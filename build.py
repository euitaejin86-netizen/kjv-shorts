"""대본 JSON 하나를 받아 9:16 묵상 쇼츠 MP4를 만든다.

영상 구성 순서는 고정이다:
  1. 구절 카드 (무음, VERSE_CARD_SEC 초)
  2. 영어 구절 낭독
  3. 한글 구절 낭독
  4. 묵상 해설 (문장 단위)
"""
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "out"

VOICE_KO = "ko-KR-InJoonNeural"
VOICE_EN = "en-GB-RyanNeural"

W, H, FPS = 1080, 1920, 30
VERSE_CARD_SEC = 2.0   # 구절 카드를 읽을 시간. 쇼츠 피드의 썸네일 역할도 한다.
GAP_SEC = 0.4          # 문장 사이 간격

REQUIRED = ("topic", "ref", "verse_ko", "verse_en", "narration", "bg")


def load_script(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ValueError(f"{path.name}: 필드 누락 {missing}")
    if not isinstance(data["narration"], list) or not data["narration"]:
        raise ValueError(f"{path.name}: narration은 비어 있지 않은 문장 배열이어야 한다")
    if not (ROOT / data["bg"]).exists():
        raise FileNotFoundError(f"{path.name}: 배경 이미지 없음 {data['bg']}")
    return data


async def _tts(text: str, voice: str, out: Path):
    await edge_tts.Communicate(text=text, voice=voice).save(str(out))


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    """ffmpeg/ffprobe 실행 래퍼.

    subprocess.run(check=True)의 CalledProcessError는 기본 str()에 stderr를
    담지 않는다 (반환코드만 보인다). 실패하면 stderr를 그대로 예외 메시지에
    담아 던져서 설계 문서 §10의 "FFmpeg 실패: stderr 그대로 노출"을 지킨다.
    """
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{result.stderr}")
    return result.stdout


def synth(text: str, voice: str, out: Path) -> float:
    """문장 하나를 음성으로 만들고 실제 재생 길이를 초 단위로 돌려준다."""
    asyncio.run(_tts(text, voice, out))
    stdout = _run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(out)],
    )
    return float(stdout.strip())


def ass_time(sec: float) -> str:
    h, rem = divmod(max(sec, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_ass(segments: list[tuple[float, float, str]], path: Path):
    """자막 파일을 만든다. drawtext는 한글 자동 줄바꿈이 안 되므로 ASS를 쓴다."""
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,Malgun Gothic,64,&H00FFFFFF,&H00000000,&H80000000,1,1,4,2,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [
        f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Main,,0,0,0,,{t}"
        for a, b, t in segments
    ]
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


def build(script_path: Path) -> Path:
    data = load_script(script_path)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_mp4 = OUT_DIR / (script_path.stem + ".mp4")

    work = Path(tempfile.mkdtemp(prefix="kjvshorts_"))
    try:
        # 1. 무음 카드 + 각 문장 음성 생성
        silence = work / "000_silence.mp3"
        _run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", str(VERSE_CARD_SEC), "-q:a", "9", str(silence)],
        )

        pieces = [(silence, VERSE_CARD_SEC, f"{data['verse_ko']}\\N\\N— {data['ref']}")]
        jobs = [(data["verse_en"], VOICE_EN), (data["verse_ko"], VOICE_KO)]
        jobs += [(s, VOICE_KO) for s in data["narration"]]

        for i, (text, voice) in enumerate(jobs, 1):
            mp3 = work / f"{i:03d}.mp3"
            dur = synth(text, voice, mp3)
            pieces.append((mp3, dur, text))

        # 2. 자막 타이밍은 실제 음성 길이로 정한다
        segments, t = [], 0.0
        for _mp3, dur, text in pieces:
            segments.append((t, t + dur, text))
            t += dur + GAP_SEC
        total = t

        write_ass(segments, work / "sub.ass")

        # 3. 음성을 순서대로 이어 붙인다 (사이에 GAP_SEC 무음)
        gap = work / "gap.mp3"
        _run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", str(GAP_SEC), "-q:a", "9", str(gap)],
        )
        listing = []
        for mp3, _dur, _text in pieces:
            listing.append(f"file '{mp3.name}'")
            listing.append(f"file '{gap.name}'")
        (work / "concat.txt").write_text("\n".join(listing) + "\n", encoding="utf-8")
        _run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
             "-c", "copy", "audio.mp3"],
            cwd=work,
        )

        # 4. Ken Burns 배경 + 자막 + 음성 -> MP4
        #    subtitles 필터는 Windows 절대경로의 콜론 이스케이프가 까다로우므로
        #    작업 디렉터리를 work로 두고 파일명만 넘긴다.
        shutil.copy(ROOT / data["bg"], work / "bg.jpg")
        vf = (
            # 실제 해상도의 2배로 키운 뒤 크롭: zoompan이 확대해도 원본 경계가
            # 드러나지 않도록 여유 픽셀을 확보한다 (대신 리샘플링으로 약간 부드러워진다).
            f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,"
            f"crop={W*2}:{H*2},"
            # Ken Burns: 프레임마다 0.00035씩 확대 (fps=30 기준 초당 약 1%), 1.18배에서 멈춰
            # 확대해도 크롭 여유분 밖(원본 경계)이 보이지 않게 한다.
            f"zoompan=z='min(1+0.00035*on,1.18)'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={W}x{H}:fps={FPS},"
            f"subtitles=sub.ass"
        )
        # 최종 출력은 out_mp4에 바로 쓰지 않고 work 안에서 먼저 만든다.
        # 인코딩이 도중에 실패해도 (mp4 먹서는 파일을 초기화 시점에 미리 만들기 때문에)
        # out/ 아래의 기존 결과물이 부분 인코딩된 파일로 덮어써지지 않는다.
        tmp_mp4 = work / "out.mp4"
        subprocess.run(
            # image2 디먹서는 -framerate를 안 주면 기본 25fps로 정지 이미지를 읽는다.
            # 아래 zoompan의 fps=30과 어긋나면 (d=1이라 프레임 복제를 안 하므로)
            # 출력 길이가 25/30배로 조용히 줄어든다 (오디오는 안 줄어서 뒷부분이 잘림).
            # 반드시 FPS와 같은 값을 준다.
            ["ffmpeg", "-y", "-framerate", str(FPS), "-loop", "1", "-t", f"{total:.2f}", "-i", "bg.jpg",
             "-i", "audio.mp3", "-vf", vf,
             "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-shortest", str(tmp_mp4)],
            cwd=work, check=True,
        )
        shutil.move(str(tmp_mp4), str(out_mp4))
    except Exception:
        # 이번 실행이 실패했을 때만 작업 파일을 남긴다. out_mp4.exists()는 이전 실행의
        # 성공 결과물일 수도 있어 "이번 실행 성공 여부"의 근거가 될 수 없으므로 쓰지 않는다
        # (finally에서 .exists()로 판단하면, 이전 성공 결과가 남아있는 상태에서 재실행이
        # 실패해도 성공으로 오판해 이번 실행의 작업 폴더를 지워버린다).
        print(f"작업 파일을 남겨 둠: {work}", file=sys.stderr)
        raise
    shutil.rmtree(work, ignore_errors=True)
    return out_mp4


def main():
    paths = [Path(a) for a in sys.argv[1:]]
    if not paths:
        print("usage: python build.py scripts/<name>.json [...]", file=sys.stderr)
        raise SystemExit(2)
    for p in paths:
        try:
            print(f"built {build(p)}")
        except Exception as e:
            # 대본 하나가 실패해도 나머지 배치는 계속 만든다
            print(f"FAILED {p.name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
