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
SUB_FADE_MS = 200      # 자막 페이드 인/아웃 길이 (ms)
BGM_VOLUME = 0.22      # 배경음악 기본 크기 (0~1). 내레이션이 나오면 사이드체인으로 추가로 낮아진다.

# upload.py의 REQUIRED와 같은 대본 스키마를 검사한다 (build.py는 렌더링에
# "bg"가 더 필요하다). 두 파일은 서로 import하지 않으므로(모듈 경계) 상수를
# 공유하지 않는다 — 필드를 바꾸면 이 파일과 upload.py:25 둘 다 고친다.
REQUIRED = ("topic", "ref", "verse_ko", "verse_en", "narration", "bg")
# "bgm"은 선택 필드다: 없으면 기존처럼 배경음악 없이 렌더링한다 (하위 호환).


def load_script(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ValueError(f"{path.name}: 필드 누락 {missing}")
    if not isinstance(data["narration"], list) or not data["narration"]:
        raise ValueError(f"{path.name}: narration은 비어 있지 않은 문장 배열이어야 한다")
    if not (ROOT / data["bg"]).exists():
        raise FileNotFoundError(f"{path.name}: 배경 이미지 없음 {data['bg']}")
    if data.get("bgm") and not (ROOT / data["bgm"]).exists():
        raise FileNotFoundError(f"{path.name}: 배경음악 없음 {data['bgm']}")
    return data


async def _tts(text: str, voice: str, out: Path):
    await edge_tts.Communicate(text=text, voice=voice).save(str(out))


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    """ffmpeg/ffprobe 실행 래퍼.

    subprocess.run(check=True)의 CalledProcessError는 기본 str()에 stderr를
    담지 않는다 (반환코드만 보인다). 실패하면 stderr를 그대로 예외 메시지에
    담아 던져서 설계 문서 §10의 "FFmpeg 실패: stderr 그대로 노출"을 지킨다.
    """
    # encoding/errors 명시: 안 주면 Windows cp949 콘솔에서 ffmpeg stderr의
    # UTF-8 바이트를 못 읽어 UnicodeDecodeError가 나면서 정작 보여줘야 할
    # 실패 원인(§10)이 가려진다.
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
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


def _ass_escape(text: str) -> str:
    """ASS Dialogue 줄에 원문을 넣기 전 이스케이프한다.

    verse_ko/verse_en(성경 본문)은 31,102절 전수 확인 결과 `{` `}` `\\` 개행이
    전혀 없어 안전하지만, narration은 자유 텍스트라 중괄호가 섞이면 ASS
    태그로 오인되고 개행이 섞이면 줄이 깨진다. 방어적으로 항상 이스케이프한다.
    """
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\r\n", "\\N")
        .replace("\n", "\\N")
    )


def segment_timings(
    pieces: list[tuple[Path, float, str]], gap: float = GAP_SEC
) -> tuple[list[tuple[float, float, str]], float]:
    """pieces(mp3, 실제 재생 길이, 자막 텍스트)를 GAP_SEC 간격으로 순서대로
    이어 붙였을 때 각 구간의 시작·끝 시각과 총 길이를 계산한다.

    자막이 실제 오디오 위에 정확히 겹치는지를 결정하는 유일한 계산이라
    순수 함수로 분리해 (ffmpeg 없이) 테스트한다.
    """
    segments: list[tuple[float, float, str]] = []
    t = 0.0
    for _mp3, dur, text in pieces:
        segments.append((t, t + dur, text))
        t += dur + gap
    return segments, t


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
    fade = f"{{\\fad({SUB_FADE_MS},{SUB_FADE_MS})}}"
    lines = [
        f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Main,,0,0,0,,{fade}{t}"
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

        pieces = [(
            silence, VERSE_CARD_SEC,
            f"{_ass_escape(data['verse_ko'])}\\N\\N— {_ass_escape(data['ref'])}",
        )]
        jobs = [(data["verse_en"], VOICE_EN), (data["verse_ko"], VOICE_KO)]
        jobs += [(s, VOICE_KO) for s in data["narration"]]

        for i, (text, voice) in enumerate(jobs, 1):
            mp3 = work / f"{i:03d}.mp3"
            dur = synth(text, voice, mp3)  # TTS는 원문 그대로 읽는다 (이스케이프 전)
            pieces.append((mp3, dur, _ass_escape(text)))

        # 2. 자막 타이밍은 실제 음성 길이로 정한다
        segments, total = segment_timings(pieces)

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

        # 4. Ken Burns 배경 + 자막 + 음성(+배경음악) -> MP4
        #    subtitles 필터는 Windows 절대경로의 콜론 이스케이프가 까다로우므로
        #    작업 디렉터리를 work로 두고 파일명만 넘긴다.
        shutil.copy(ROOT / data["bg"], work / "bg.jpg")
        video_chain = (
            # 실제 해상도의 2배로 키운 뒤 크롭: zoompan이 확대해도 원본 경계가
            # 드러나지 않도록 여유 픽셀을 확보한다 (대신 리샘플링으로 약간 부드러워진다).
            f"[0:v]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,"
            f"crop={W*2}:{H*2},"
            # Ken Burns: 프레임마다 0.00035씩 확대 (fps=30 기준 초당 약 1%), 1.18배에서 멈춰
            # 확대해도 크롭 여유분 밖(원본 경계)이 보이지 않게 한다.
            f"zoompan=z='min(1+0.00035*on,1.18)'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={W}x{H}:fps={FPS},"
            f"subtitles=sub.ass[vout]"
        )

        cmd = ["ffmpeg", "-y",
               # image2 디먹서는 -framerate를 안 주면 기본 25fps로 정지 이미지를 읽는다.
               # 아래 zoompan의 fps=30과 어긋나면 (d=1이라 프레임 복제를 안 하므로)
               # 출력 길이가 25/30배로 조용히 줄어든다 (오디오는 안 줄어서 뒷부분이 잘림).
               # 반드시 FPS와 같은 값을 준다.
               "-framerate", str(FPS), "-loop", "1", "-t", f"{total:.2f}", "-i", "bg.jpg",
               "-i", "audio.mp3"]

        bgm = data.get("bgm")
        if bgm:
            shutil.copy(ROOT / bgm, work / "bgm.mp3")
            # -stream_loop -1: 배경음악이 total보다 짧아도 반복해서 채운다.
            # 뒤의 -shortest가 정확한 길이로 잘라준다.
            cmd += ["-stream_loop", "-1", "-i", "bgm.mp3"]
            audio_chain = (
                f"[2:a]volume={BGM_VOLUME}[bgm];"
                # 내레이션(1:a)이 나오는 동안 배경음악을 사이드체인 컴프레션으로
                # 추가로 낮춘다(더킹). threshold/ratio는 TTS 음성 레벨 기준의
                # 경험적 기본값이다 — 다른 음원으로 바꾸면 귀로 다시 맞춘다.
                f"[bgm][1:a]sidechaincompress=threshold=0.03:ratio=15:attack=5:release=400[bgm_duck];"
                # amix는 기본(normalize=1)으로 클리핑 방지를 위해 각 입력을
                # 자동으로 줄인다 — 그러면 bgm이 있을 때만 내레이션 음성 자체가
                # 조용해져 bgm 유무에 따라 목소리 크기가 달라진다. normalize=0으로
                # 꺼서 내레이션은 원래 볼륨 그대로 두고 이미 더킹된 bgm만 얹는다.
                f"[1:a][bgm_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
            )
            filter_complex = video_chain + ";" + audio_chain
            cmd += ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"]
        else:
            cmd += ["-filter_complex", video_chain, "-map", "[vout]", "-map", "1:a"]

        # 최종 출력은 out_mp4에 바로 쓰지 않고 work 안에서 먼저 만든다.
        # 인코딩이 도중에 실패해도 (mp4 먹서는 파일을 초기화 시점에 미리 만들기 때문에)
        # out/ 아래의 기존 결과물이 부분 인코딩된 파일로 덮어써지지 않는다.
        tmp_mp4 = work / "out.mp4"
        cmd += ["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-shortest", str(tmp_mp4)]
        subprocess.run(cmd, cwd=work, check=True)
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
