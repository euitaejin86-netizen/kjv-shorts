"""대본 JSON 하나를 받아 9:16 묵상 쇼츠 MP4를 만든다.

영상 구성 순서는 고정이다:
  1. 훅 카드 (있으면) — 문구를 먼저 띄워 스크롤을 멈춘다
  2. 구절 카드 (무음, VERSE_CARD_SEC 초)
  3. 영어 구절 낭독
  4. 한글 구절 낭독
  5. 묵상 해설 (문장 단위)
  6. 아웃트로 카드 (있으면)

연출은 내용과 분리된 "템플릿"으로 제어한다. 대본 JSON에 "template": "자극형"
같이 templates/*.json 을 지정하면 그 파일의 레이아웃 규칙(자막 위치·크기·2색·
레터박스·글자수 등)을 따른다. 지정하지 않으면 기존 고정 연출을 그대로 재현한다
(하위 호환). 대본의 "style" 인라인 필드로 템플릿의 일부를 덮어쓸 수도 있다.

배경(`bg`)은 이미지 한 장(문자열, 기존 대본과 하위 호환)이거나 여러 장(리스트)일
수 있다. 여러 장이면 영상 길이를 장 수만큼 균등하게 나눠 순서대로 전환한다.
"""
import asyncio
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "out"

VOICE_KO = "ko-KR-HyunsuMultilingualNeural"
VOICE_EN = "en-GB-RyanNeural"
KO_RATE, KO_PITCH = "+8%", "-2Hz"
# 낭독 마스터링: 저음 정리 → 선명도 → 압축 → 약한 공간감 → 유튜브 표준 음량(-14 LUFS)
VOICE_MASTER = (
    "highpass=f=90,equalizer=f=250:t=q:w=1:g=-2,equalizer=f=3500:t=q:w=1.2:g=3,"
    "acompressor=threshold=-20dB:ratio=3:attack=5:release=120:makeup=2,"
    "aecho=0.8:0.6:35:0.08,loudnorm=I=-14:TP=-1.5:LRA=7"
)

W, H, FPS = 1080, 1920, 30
VERSE_CARD_SEC = 2.0   # 구절 카드를 읽을 시간. 쇼츠 피드의 썸네일 역할도 한다.
GAP_SEC = 0.4          # 문장 사이 간격
SUB_FADE_MS = 200      # 자막 페이드 인/아웃 길이 (ms)
OUTRO_SEC = 3.0        # 마지막 아웃트로(시그니처) 카드 길이. 0이면 아웃트로 없음.
BGM_FADE_SEC = 1.8     # 배경음악 마지막 페이드아웃 길이 (s). 뚝 끊기는 엔딩 방지.
BGM_VOLUME = 0.22

# ASS 강조색 (BGR 0x00BBGGRR). 흰색 본문에 금색 핵심 문구, 은색 주소.
GOLD = "&H00C8E0&"      # 금색 (B=00 G=C8 R=E0)
YELLOW = "&H00FFD700&"  # 밝은 노랑/골드 (벤치마크 2색 #FFD700)
SILVER = "&H00D0D0D0&"  # 은색
WHITE = "&H00FFFFFF&"   # 흰색

# 자막 유형. 각 유형이 템플릿에서 독립적인 스타일을 가질 수 있다.
KIND_HOOK = "hook"
KIND_VERSE = "verse"
KIND_NARRATION = "narration"
KIND_OUTRO = "outro"

# 자막을 띄우는 y 정렬. ASS Alignment 값이다.
_ALIGN = {"top": 8, "center": 5, "bottom": 2}

# upload.py의 REQUIRED와 같은 대본 스키마를 검사한다 (build.py는 렌더링에
# "bg"가 더 필요하다). 두 파일은 서로 import하지 않으므로(모듈 경계) 상수를
# 공유하지 않는다 — 필드를 바꾸면 이 파일과 upload.py:25 둘 다 고친다.
REQUIRED = ("topic", "ref", "verse_ko", "verse_en", "narration", "bg")
# "bgm"은 선택 필드다: 없으면 기존처럼 배경음악 없이 렌더링한다 (하위 호환).


def is_video(path) -> bool:
    """배경 항목이 이미지(.jpg/.png)인지 동영상(.mp4/.webm)인지 판별."""
    return str(path).lower().endswith(('.mp4', '.webm', '.mov'))


def is_image(path) -> bool:
    return str(path).lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))


def bg_list(data: dict) -> list[str]:
    """대본의 ``bg`` 필드를 항상 리스트로 정규화한다.

    ``scenes[].media``를 쓰는 새 대본은 bg가 없어도 된다. 이 경우 장면 미디어가
    렌더 배경이 되고, 기존 bg는 하위 호환 fallback으로만 남는다.
    """
    bg = data.get("bg", [])
    if not bg:
        return []
    return [bg] if isinstance(bg, str) else list(bg)


def scene_list(data: dict) -> list[dict]:
    """모든 verse 블록의 scenes를 순서대로 평탄화한다."""
    blocks = data.get("verses")
    if blocks is None:
        return list(data.get("scenes") or [])
    return [scene for block in blocks for scene in (block.get("scenes") or [])]


def visual_segments(data: dict, pieces: list[tuple], total: float) -> list[dict]:
    """실제 TTS 조각 길이에 맞춘 장면별 시각 타임라인을 계산한다.

    반환 요소: ``{media, duration, motion, camera, mood, visual_prompt}``.
    새 ``scenes``가 있으면 hook → verse → scene별 TTS → outro 순서를 그대로 따라가며,
    scenes가 없으면 종전의 bg 균등분할 방식을 유지한다.
    """
    scenes = scene_list(data)
    if not scenes:
        bgs = bg_list(data)
        has_hook = bool(data.get("hook"))
        hook_bg = data.get("hook_bg") if has_hook else None
        hook_len = pieces[0][1] + GAP_SEC if pieces and has_hook else 0.0
        out = []
        if hook_bg and hook_len > 0:
            out.append({"media": hook_bg, "duration": hook_len, "motion": "auto"})
            durs = bg_segment_durations(total - hook_len, len(bgs))
            out.extend({"media": bg, "duration": dur, "motion": "auto"} for bg, dur in zip(bgs, durs))
        else:
            durs = bg_segment_durations(total, len(bgs))
            out.extend({"media": bg, "duration": dur, "motion": "auto"} for bg, dur in zip(bgs, durs))
        return out

    # pieces 순서: hook? + 각 block의 verse + 각 scene + outro?
    cursor = 0
    out: list[dict] = []
    fallback = bg_list(data)
    fallback_i = 0
    if data.get("hook"):
        p = pieces[cursor]; cursor += 1
        media = data.get("hook_bg") or (fallback[fallback_i % len(fallback)] if fallback else scenes[0]["media"])
        fallback_i += 1
        out.append({"media": media, "duration": p[1] + GAP_SEC, "motion": "none"})

    blocks = data.get("verses") or [data]
    for block in blocks:
        # verse 낭독 카드
        p = pieces[cursor]; cursor += 1
        block_scenes = block.get("scenes") or []
        media = block.get("verse_bg") or data.get("verse_bg")
        if not media:
            media = block_scenes[0]["media"] if block_scenes else fallback[fallback_i % len(fallback)]
        fallback_i += 1
        out.append({"media": media, "duration": p[1] + GAP_SEC, "motion": "auto"})
        for scene in block_scenes:
            p = pieces[cursor]; cursor += 1
            item = dict(scene)
            item["duration"] = p[1] + GAP_SEC
            item.setdefault("motion", "auto")
            out.append(item)

    if data.get("outro"):
        p = pieces[cursor]
        media = data.get("outro_bg") or scenes[-1]["media"]
        out.append({"media": media, "duration": p[1] + GAP_SEC, "motion": "zoom_out"})

    # 부동소수점·concat 오차를 마지막 장면이 흡수한다.
    drift = total - sum(x["duration"] for x in out)
    out[-1]["duration"] += drift
    return out


def image_motion_filter(input_idx: int, motion: str) -> str:
    """정적 이미지에 장면별 Ken Burns 카메라 움직임을 적용한다."""
    z_in = "min(1+0.00035*on,1.18)"
    z_out = "max(1.18-0.00035*on,1.0)"
    z = z_out if motion == "zoom_out" else z_in
    if motion == "none":
        z = "1.0"
    if motion == "pan_left":
        x = "max(iw/zoom-iw*0.18-on*1.2,0)"
    elif motion == "pan_right":
        x = "min(on*1.2,iw-iw/zoom)"
    else:
        x = "iw/2-(iw/zoom/2)"
    y = "ih/2-(ih/zoom/2)"
    return (
        f"[{input_idx}:v]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,"
        f"crop={W*2}:{H*2},zoompan=z='{z}':x='{x}':y='{y}'"
        f":d=1:s={W}x{H}:fps={FPS}[v{input_idx}]"
    )


def _default_layout() -> dict:
    """template 지정이 없을 때 쓰는 기본 레이아웃.

    기존 고정 연출(96px 상단 자막, 흰 본문+금강조, 은 주소)을 그대로 재현하도록
    값이 잡혀 있다 — 템플릿 전환 이후로도 구버전 대본 렌더가 달라지지 않게 한다.
    """
    return {
        "id": "기본",
        "letters": {"top": 0, "bottom": 0},
        "colors": {"white": WHITE, "gold": GOLD, "silver": SILVER},
        "styles": {
            KIND_HOOK: {"align": "top", "size": 96, "body": "gold",
                        "highlight": "white", "margin_v": 90, "wrap": 0,
                        "outline": 6, "shadow": 3},
            KIND_VERSE: {"align": "top", "size": 96, "body": "gold",
                         "highlight": "white", "margin_v": 90, "wrap": 0,
                         "outline": 6, "shadow": 3},
            KIND_NARRATION: {"align": "top", "size": 96, "body": "white",
                             "highlight": "gold", "margin_v": 90, "wrap": 0,
                             "outline": 6, "shadow": 3},
            KIND_OUTRO: {"align": "top", "size": 96, "body": "gold",
                         "highlight": "white", "margin_v": 90, "wrap": 0,
                         "outline": 6, "shadow": 3},
        },
        "duration_target_s": [0, 0],
    }


def load_layout(data: dict) -> dict:
    """대본의 "template"/"style" 필드에서 레이아웃 규칙을 계산한다.

    우선순위(낮은 순 → 높은 순): 기본 > templates/<id>.json > 대본 인라인 "style".
    대본 JSON의 style은 dict이며 템플릿과 같은 형태(styles/letters/colors)를 가질
    수 있고, 없으면 템플릿을 그대로 쓴다.
    """
    layout = _default_layout()
    tpl = data.get("template")
    if tpl:
        p = ROOT / "templates" / f"{tpl}.json"
        if not p.exists():
            raise FileNotFoundError(f"템플릿 없음: {p}")
        t = json.loads(p.read_text(encoding="utf-8"))
        layout = _merge_layout(layout, t)
    # 인라인 style 오버라이드
    if data.get("style"):
        layout = _merge_layout(layout, data["style"])
    return layout


def _merge_layout(base: dict, override: dict) -> dict:
    """레이아웃 두 개를 shallow-merge한다. styles/letters/colors는 키 단위로 합친다."""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            merged = dict(out[k])
            merged.update(v)
            out[k] = merged
        else:
            out[k] = v
    return out


def load_script(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("verses") is not None:
        # 다절 통합본: 각 블록이 verse_ko/verse_en/narration을 갖고 있어야 한다.
        if not isinstance(data["verses"], list) or not data["verses"]:
            raise ValueError(f"{path.name}: verses는 비어 있지 않은 배열이어야 한다")
        for i, blk in enumerate(data["verses"]):
            bm = [k for k in ("ref", "verse_ko", "verse_en") if k not in blk]
            if bm:
                raise ValueError(f"{path.name}: verses[{i}] 필드 누락 {bm}")
            has_narration = isinstance(blk.get("narration"), list) and bool(blk["narration"])
            has_scenes = isinstance(blk.get("scenes"), list) and bool(blk["scenes"])
            if not (has_narration or has_scenes):
                raise ValueError(f"{path.name}: verses[{i}]에 narration 또는 scenes가 필요하다")
    else:
        missing = [k for k in ("topic", "ref", "verse_ko", "verse_en", "narration") if k not in data]
        if missing:
            raise ValueError(f"{path.name}: 필드 누락 {missing}")
        if not isinstance(data["narration"], list) or not data["narration"]:
            raise ValueError(f"{path.name}: narration은 비어 있지 않은 문장 배열이어야 한다")
    bgs = bg_list(data)
    scenes = scene_list(data)
    if not bgs and not scenes:
        raise ValueError(f"{path.name}: bg 또는 scenes는 최소 하나 이상이어야 한다")
    scene_media = [s.get("media") for s in scenes if s.get("media")]
    missing_bg = [b for b in bgs + scene_media if not (ROOT / b).exists()]
    if missing_bg:
        raise FileNotFoundError(f"{path.name}: 배경 이미지 없음 {missing_bg}")
    if data.get("bgm") and not (ROOT / data["bgm"]).exists():
        raise FileNotFoundError(f"{path.name}: 배경음악 없음 {data['bgm']}")
    from qa_gate import validate_script_data
    for warning in validate_script_data(data, path):
        print(f"[QA] {path.name}: {warning}", file=sys.stderr)
    return data


async def _tts(text: str, voice: str, out: Path):
    # 한국어 낭독은 쇼츠 템포에 맞게 약간 빠르고 낮게 (2026-11-07 B안)
    kw = {"rate": KO_RATE, "pitch": KO_PITCH} if voice == VOICE_KO else {}
    await edge_tts.Communicate(text=text, voice=voice, **kw).save(str(out))


def _google_tts(text: str, out: Path, lang: str = "ko-KR", service_account: Path | None = None):
    """Google Cloud TTS(WaveNet)로 합성한다. 서비스계정 JSON이 있으면 사용.

    성공 시 mp3를 out에 쓰고, 실패는 예외로 던져 호출부(fallback)에서 처리하게 한다.
    """
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    from google.cloud import texttospeech

    SA = service_account or ROOT / "gcp-service-account.json"
    if not SA.exists():
        raise FileNotFoundError(f"Google TTS 서비스계정 없음: {SA}")

    creds = service_account.Credentials.from_service_account_file(
        str(SA), scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    # 만료 전 토큰 갱신
    if not creds.valid:
        creds.refresh(Request())

    client = texttospeech.TextToSpeechClient(credentials=creds)
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice_cfg = texttospeech.VoiceSelectionParams(
        language_code=lang,
        name="ko-KR-Wavenet-D" if lang == "ko-KR" else None,
        ssml_gender=texttospeech.SsmlVoiceGender.MALE,
    )
    audio_cfg = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.0,
        pitch=0.0,
    )
    resp = client.synthesize_speech(
        input=synthesis_input, voice=voice_cfg, audio_config=audio_cfg
    )
    out.write_bytes(resp.audio_content)
    return out


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    """ffmpeg/ffprobe 실행 래퍼.

    subprocess.run(check=True)의 CalledProcessError는 기본 str()에 stderr를
    담지 않는다 (반환코드만 보인다). 실패하면 stderr를 그대로 예외 메시지에
    담아 던져서 설계 문서 §10의 "FFmpeg 실패: stderr 그대로 노출"을 지킨다.
    """
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{result.stderr}")
    return result.stdout


def synth(text: str, voice: str, out: Path) -> float:
    """문장 하나를 음성으로 만들고 실제 재생 길이를 초 단위로 돌려준다.

    gcp-service-account.json이 ROOT에 있으면 Google Cloud TTS(WaveNet)로 합성하고,
    없거나 실패하면 edge-tts(현수 등)로 대체한다 — 키가 생기면 자동으로 품질이
    올라가고, 없어도 파이프라인이 멈추지 않는다.
    """
    sa = ROOT / "gcp-service-account.json"
    if sa.exists():
        try:
            _google_tts(text, out, service_account=sa)
        except Exception as e:
            print(f"[TTS] Google 합성 실패, edge-tts로 대체: {e}", file=sys.stderr)
            asyncio.run(_tts(text, voice, out))
    else:
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


_REF_RE = re.compile(r"^(.+?)\s+(\d+):(\d+)$")


def ref_display(ref: str) -> str:
    """""창세기 3:24" 같은 콜론 표기 ref를 "창세기 3장 24절" 형식으로 바꾼다.

    ref 필드 자체(콜론 표기)는 upload.py 제목 등 다른 곳에서도 그대로 쓰이므로
    건드리지 않고, 화면에 보여줄 때만 이 함수를 거친다. 형식이 예상과 다르면
    (책 이름에 공백이 여러 번 들어가는 등) 원문을 그대로 돌려준다.
    """
    m = _REF_RE.match(ref)
    if not m:
        return ref
    book, chap, verse = m.groups()
    return f"{book} {chap}장 {verse}절"


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


def wrap_lines(text: str, chars: int) -> list[str]:
    """글자수 제한으로 텍스트를 여러 줄로 나눈다. chars<=0 이면 그대로 한 줄.

    공백 기준으로 단어를 끊어 너비를 만족시키고, 한 단어가 chars를 넘으면
    단어 내부에서 강제로 나눈다. 반환값은 (아직 이스케이프 전) raw 줄들이다 —
    각 줄을 개별적으로 apply_highlight 처리한 뒤 `\\N`로 이어 붙인다. 이렇게
    하면 색 태그가 줄 사이로 뚫리지 않는다.
    """
    if chars <= 0:
        return [text]
    words = text.split()
    if not words:
        return [text]
    lines: list[str] = []
    cur = ""
    for w in words:
        # 단어 하나가 chars보다 길면 강제 분할
        while len(w) > chars:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(w[:chars])
            w = w[chars:]
        if cur and len(cur) + 1 + len(w) > chars:
            lines.append(cur)
            cur = w
        elif cur:
            cur += " " + w
        else:
            cur = w
    if cur:
        lines.append(cur)
    return lines


def apply_highlight(text: str, highlights: list[str],
                    body: str = WHITE, hl: str = GOLD) -> str:
    """이스케이프된 텍스트에서 highlight 목록에 일치하는 문구만 강조색으로 감싼다.

    첫 줄만 escape 한 뒤 highlight를 적용한다. 여러 줄이면 wrap_lines로 나눈
    뒤 각 줄마다 이 함수를 쓰고 호출부에서 `\\N`로 이어 붙인다.
    """
    esc = _ass_escape(text)
    if not highlights:
        return esc
    for h in sorted(highlights, key=len, reverse=True):
        he = _ass_escape(h)
        if he and he in esc:
            esc = esc.replace(he, "{\\c" + hl + "}" + he + "{\\c" + body + "}")
    return esc


def _styled_text(kind: str, text: str, highlights: list[str], layout: dict,
                 ref: str = "") -> tuple[str, str]:
    """유형별 본문 색·강조색을 반영해 ASS 텍스트를 만들고 스타일명을 돌려준다.

    반환: (스타일명, 대화줄 Text). Text는 이미 이스케이프+강조 적용된 상태.
    text는 새줄을 실제 ``\\n``으로 담은 raw 줄들이다 — _ass_escape가 `\\n`을
    ASS 개행 `\\N`(단일 백슬래시)으로 바꾸므로 이중 백슬래시가 생기지 않는다.

    verse는 ref(주소)를 ``\\N(ref)`` 꼴로 은색 덧붙인다 (구버전과 동일 연출).
    """
    st = layout["styles"][kind]
    col = layout["colors"]
    body = col[st.get("body", "white")]
    hl = col[st.get("highlight", "gold")]

    if kind in (KIND_HOOK, KIND_OUTRO):
        # 훅/아웃트로: 특정 단어 강조가 있으면 그 단어만 홀로, 없으면 전체를 본문색.
        if highlights:
            return kind, "{%s}" % body + apply_highlight(text, highlights, body, hl)
        return kind, "{%s}" % body + _ass_escape(text)
    if kind == KIND_VERSE:
        # 절: 본문을 본문색으로, (주소)는 은색. ref는 텍스트에 포함되지 않고
        # 여기서 ``\N(ref)`` 꼴로 이어 붙인다 (어차피 _ass_escape는 개행을 단일
        # ``\N``으로 만들므로, 여기서는 이미 이스케이프된 뒤 상태로 은색 처리).
        esc_body = _ass_escape(text)
        esc_ref = _ass_escape(ref)
        return kind, "{%s}" % body + esc_body + "{%s}" % col["silver"] + "\\N(" + esc_ref + ")"
    # 해설: 본문 색, 강조색만 hl.
    return kind, apply_highlight(text, highlights, body, hl)


KIND_COMPARE = "compare"   # 개역개정 ↔ 흠정역 나란히 비교 카드 (verse 스타일 폰트 사용)
CMP_WRAP = 13              # 비교 카드 한 줄 글자수
CMP_CONTEXT = 2            # 차이 문구 앞에 보여줄 단어 수
CMP_AFTER = 0              # 차이 문구 뒤에 보여줄 단어 수 (0이면 문장부호 + …)
CMP_FALLBACK_WORDS = 7     # 차이 문구를 못 찾으면 앞에서부터 보여줄 단어 수
CMP_KRV = "&H00A0A0A0&"    # 개역개정 본문: 흐린 회색
CMP_STRIKE = "&H006060E0&" # 바뀐/사라진 부분: 붉은 취소선 (BGR)


def excerpt(verse: str, phrase: str | None) -> tuple[str, str, str]:
    """구절에서 차이 문구 주변만 잘라 (앞, 문구, 뒤)를 돌려준다.

    문구 앞뒤로 CMP_CONTEXT 단어만 남기고 잘린 쪽에 "…"를 붙인다. 문구에 붙은
    문장부호("하느냐?")는 떼지 않는다. 문구가 없으면 앞 CMP_FALLBACK_WORDS 단어.
    """
    if not phrase or phrase not in verse:
        words = verse.split()
        tail = " …" if len(words) > CMP_FALLBACK_WORDS else ""
        return " ".join(words[:CMP_FALLBACK_WORDS]) + tail, "", ""
    i = verse.index(phrase)
    before, after = verse[:i], verse[i + len(phrase):]
    head_att = re.search(r"\S*$", before).group()
    tail_att = re.match(r"\S*", after).group()
    bw = before[:len(before) - len(head_att)].split()
    aw = after[len(tail_att):].split()
    pre = " ".join(bw[-CMP_CONTEXT:])
    post = " ".join(aw[:CMP_AFTER])
    pre = ("… " if len(bw) > CMP_CONTEXT else "") + pre + (" " if pre else "") + head_att
    post = tail_att + (" " + post if post else "") + ("…" if len(aw) > CMP_AFTER else "")
    return pre, phrase, post


def _cmp_lines(pre: str, phrase: str, post: str, base: str, mark: str) -> str:
    """excerpt 결과를 줄바꿈하고, 문구가 걸친 글자 구간만 줄마다 mark 태그로 감싼다.
    문구가 한 줄보다 길어 여러 줄에 걸쳐도 강조가 끊기지 않는다."""
    full = pre + phrase + post
    a, b = len(pre), len(pre) + len(phrase)
    out, cur = [], 0
    for ln in wrap_lines(full, CMP_WRAP):
        i = full.find(ln, cur)
        cur = i + len(ln)
        lo, hi = max(a, i) - i, min(b, cur) - i
        if phrase and lo < hi:
            out.append(_ass_escape(ln[:lo]) + mark + _ass_escape(ln[lo:hi]) + base + _ass_escape(ln[hi:]))
        else:
            out.append(_ass_escape(ln))
    return "\\N".join(out)


def compare_card(block: dict, ref_disp: str, col: dict) -> tuple[str, int]:
    """개역개정(위, 회색·취소선) → 흠정역(아래, 흰색·금색 강조) 비교 카드 ASS 텍스트와
    대략적인 높이(px)를 만든다. verse_krv가 "(없음)"이면 빈 절을 크게 보여준다."""
    hls = block.get("highlight") or []
    kjv, krv = block["verse_ko"], block["verse_krv"]
    kjv_hl = next((h for h in hls if h in kjv), None)
    krv_hl = next((h for h in hls if h in krv), None)
    gold, white, silver = col["gold"], col["white"], col["silver"]

    if krv.strip() in ("", "(없음)", "없음"):
        krv_txt = "{\\fs84\\c%s}( 없음 )\\N{\\fs44}이 절이 통째로 없습니다" % CMP_STRIKE
        krv_lines = 2.6
    else:
        base = "{\\s0\\c%s}" % CMP_KRV
        # 흠정역 쪽 강조가 없으면 "개역개정도 그대로 둔" 보존 사례 → 취소선 대신 금색.
        mark = "{\\s1\\c%s}" % CMP_STRIKE if kjv_hl else "{\\c%s}" % gold
        body = _cmp_lines(*excerpt(krv, krv_hl), base, mark)
        krv_txt = "{\\fs72}" + base + body
        krv_lines = body.count("\\N") + 1
    base = "{\\c%s}" % white
    body = _cmp_lines(*excerpt(kjv, kjv_hl), base, "{\\c%s}" % gold)
    kjv_lines = body.count("\\N") + 1

    text = (
        "{\\fs46\\c%s}개역개정\\N" % silver + krv_txt
        + "\\N{\\fs64\\c%s}↓\\N" % gold
        + "{\\fs46\\c%s}흠정역 (KJV)\\N{\\fs80}" % gold + base + body
        + "\\N{\\fs42\\c%s}%s" % (silver, _ass_escape(ref_disp))
    )
    # ponytail: 높이는 줄수×폰트 어림값 — 글꼴 바꾸면 계수만 조정
    height = int(46 * 2 + 72 * krv_lines + 64 + 80 * kjv_lines + 42 + 110)
    return text, height


def segment_timings(
    pieces: list[tuple[Path, float, str, str, list, str]], gap: float = GAP_SEC,
) -> tuple[list[tuple[float, float, str, str, list, str]], float]:
    """pieces(mp3, 재생길이, kind, 자막 raw, highlight, ref)를 GAP_SEC 간격으로
    순서대로 이어 붙였을 때 각 구간의 시작·끝 시각과 총 길이를 계산한다.

    자막이 실제 오디오 위에 정확히 겹치는지를 결정하는 유일한 계산이라
    순수 함수로 분리해 (ffmpeg 없이) 테스트한다.
    """
    segments: list[tuple[float, float, str, str, list, str]] = []
    t = 0.0
    for _mp3, dur, kind, text, hl, ref in pieces:
        segments.append((t, t + dur, kind, text, hl, ref))
        t += dur + gap
    return segments, t


def bg_segment_durations(total: float, n: int) -> list[float]:
    """total 초를 배경 이미지 n장에 최대한 고르게 나눈다.

    마지막 조각이 나머지를 흡수해 합이 total과 정확히 같도록 한다 (반올림
    오차로 마지막 배경이 일찍 잘리거나 영상 끝에 검은 프레임이 남는 것을 막는다).
    ffmpeg 호출 없이 테스트할 수 있게 순수 함수로 분리한다.
    """
    if n <= 0:
        raise ValueError("n은 1 이상이어야 한다")
    base = total / n
    return [base] * (n - 1) + [total - base * (n - 1)]


def write_ass(segments: list[tuple[float, float, str, str, list, str]], path: Path, layout: dict):
    """자막 파일을 만든다. 유형별 스타일 + 클립에 따른 레터박스/배치를 반영한다."""
    col = layout["colors"]
    st = layout["styles"]
    style_lines = []
    for kind in (KIND_HOOK, KIND_VERSE, KIND_NARRATION, KIND_OUTRO):
        s = st[kind]
        align = _ALIGN[s["align"]]
        # ASS 필명: Name, Fontname, Fontsize, PrimaryColour, OutlineColour,
        # BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL,
        # MarginR, MarginV, Encoding
        style_lines.append(
            f"Style: {kind},Malgun Gothic,{s['size']},{col[s['body']]},"
            f"&H00202020,&H80000000,1,1,{s['outline']},{s['shadow']},{align},"
            f"40,40,{s['margin_v']},1"
        )
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{chr(10).join(style_lines)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    fade = f"{{\\fad({SUB_FADE_MS},{SUB_FADE_MS})}}"
    lines = []
    for a, b, kind, text, hl, ref in segments:
        if kind == KIND_COMPARE:
            # text = 완성된 ASS 텍스트, hl 자리에 카드 높이(px)를 싣는다.
            box_h = hl
            pos = f"\\an5\\pos({W // 2},{H // 2})"
            lines.append(
                f"Dialogue: 0,{ass_time(a)},{ass_time(b)},{KIND_VERSE},,0,0,0,,"
                f"{fade}{{{pos}\\p1\\bord0\\shad0\\c&H000000&\\alpha&H30&}}"
                f"m 0 0 l {W - 80} 0 {W - 80} {box_h} 0 {box_h}{{\\p0}}"
            )
            lines.append(
                f"Dialogue: 1,{ass_time(a)},{ass_time(b)},{KIND_VERSE},,0,0,0,,"
                f"{fade}{{{pos}\\bord4\\shad0}}{text}"
            )
            continue
        sname, styled = _styled_text(kind, text, hl, layout, ref)
        lines.append(
            f"Dialogue: 0,{ass_time(a)},{ass_time(b)},{sname},,0,0,0,,{fade}{styled}"
        )
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


def build(script_path: Path) -> Path:
    data = load_script(script_path)
    layout = load_layout(data)
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

        ref_tag = _ass_escape(ref_display(data["ref"]))
        highlights = data.get("highlight", []) or []
        # 1) 구절 단위 처리: 단일 verse_ko(호환) 또는 verses 리스트(다절 통합본)
        #    각 블록마다 그 절의 본문 낭독 + 해당 해설(narration)이 따라온다.
        blocks = data.get("verses")
        if blocks is None:
            # 단일 대본 호환: 한 블록으로 묶는다.
            blocks = [{
                "ref": data.get("ref"),
                "verse_ko": data["verse_ko"],
                "verse_en": data.get("verse_en", ""),
                "narration": data["narration"],
            }]
        else:
            # 다중 대본: 리스트 각 항목이 이미 그 절과 해설을 담고 있어야 한다.
            if not isinstance(blocks, list) or not blocks:
                raise ValueError(f"{script_path.name}: verses는 비어 있지 않은 배열이어야 한다")

        wrap_hook = layout["styles"][KIND_HOOK]["wrap"]
        wrap_verse = layout["styles"][KIND_VERSE]["wrap"]
        wrap_narr = layout["styles"][KIND_NARRATION]["wrap"]

        # 첫 화면 훅(전체 대본 기준 하나만): 있으면 verse 카드 대신 띄운다.
        # 훅은 두 가지 방식으로 재생된다:
        #   - data["hook_voice"] 가 있으면 그 텍스트를 TTS로 낭독하고, 카드 길이가
        #     목소리 길이 + 여유로 자연히 늘어난다. (빨리 안 사라지게)
        #   - 없으면 기존처럼 무음 카드(VERSE_CARD_SEC)만 띄운다. (하위 호환)
        # 훅 자막은 항상 data["hook"] 문구를 띄운다. 낭독문구와 화면문구는 다를 수
        # 있어서 두 필드를 분리했다 — 예: 화면은 짧은 강한 문구, 음성은 그걸 풀어 읽기.
        pieces = []
        if data.get("hook"):
            hook_lines = wrap_lines(data["hook"], wrap_hook)
            hook_audio = silence
            hook_dur = VERSE_CARD_SEC
            if data.get("hook_voice"):
                hook_mp3 = work / f"hook_voice.mp3"
                voice_dur = synth(data["hook_voice"], VOICE_KO, hook_mp3)
                hook_audio = hook_mp3
                # 낭독 끝나도 잠깐 문구가 머무르도록 여유 시간을 붙인다.
                hook_dur = voice_dur + 0.6
            pieces.append((
                hook_audio, hook_dur, KIND_HOOK,
                "\n".join(hook_lines), data.get("hook_hl", []), data.get("ref", ""),
            ))

        job_idx = len(pieces) + 1
        for bi, block in enumerate(blocks):
            b_ref_disp = ref_display(block["ref"])
            blk_hl = block.get("highlight") or highlights
            # (a) 이 절의 본문 낭독: 본문색 + 은색 주소 (ref는 _styled_text가 덧붙임)
            mp3 = work / f"{job_idx:03d}.mp3"; job_idx += 1
            dur = synth(block["verse_ko"], VOICE_KO, mp3)
            if block.get("verse_krv"):
                # 낭독은 그대로, 화면만 개역개정↔흠정역 비교 카드로 바꾼다.
                card, box_h = compare_card(block, b_ref_disp, layout["colors"])
                pieces.append((mp3, dur, KIND_COMPARE, card, box_h, b_ref_disp))
            else:
                verse_lines = wrap_lines(block["verse_ko"], wrap_verse)
                pieces.append((
                    mp3, dur, KIND_VERSE, "\n".join(verse_lines), [], b_ref_disp,
                ))

            # (b) 이 절의 해설: 신형 scenes가 있으면 각 장면의 narration을 TTS 조각으로
            # 만들고, 없으면 기존 narration 배열을 그대로 사용한다.
            narr_items = block.get("scenes") or [
                {"narration": s} for s in block.get("narration", [])
            ]
            for scene in narr_items:
                s = scene["narration"]
                mp3 = work / f"{job_idx:03d}.mp3"; job_idx += 1
                dur = synth(s, VOICE_KO, mp3)
                pieces.append((mp3, dur, KIND_NARRATION, s, scene.get("highlight", blk_hl), ""))

        # 아웃트로: 마지막에 시그니처 카드(무음 + 문구)를 추가해 영상이 뚝 안 끊기게 한다.
        #   data["outro_voice"]가 있으면 그 텍스트를 TTS 낭독해 카드 길이가 자연히 늘어나고
        #   화면엔 data["outro"] 문구(구독유도)가 뜬다. 없으면 기존처럼 무음 카드(하위 호환).
        if OUTRO_SEC > 0 and data.get("outro"):
            outro_audio = work / "outro.mp3"
            o_dur = OUTRO_SEC
            o_text = data["outro"]
            if data.get("outro_voice"):
                outro_audio = work / "outro_voice.mp3"
                vdur = synth(data["outro_voice"], VOICE_KO, outro_audio)
                o_dur = vdur + 0.6  # 낭독 끝나고 잠깐 문구가 머무르도록 여유
            else:
                _run(
                    ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                     "-t", str(OUTRO_SEC), "-q:a", "9", str(outro_audio)],
                )
            pieces.append((
                outro_audio, o_dur, KIND_OUTRO,
                "\n".join(wrap_lines(o_text, layout["styles"][KIND_OUTRO]["wrap"])), [], "",
            ))

        # 2. 자막 타이밍은 실제 음성 길이로 정한다
        segments, total = segment_timings(pieces)

        write_ass(segments, work / "sub.ass", layout)

        # 길이 QA: 템플릿에 목표 범위가 있으면 벗어나면 경고 (실패는 아님)
        lo, hi = layout.get("duration_target_s", (0, 0))
        if hi > 0 and not (lo <= total <= hi):
            print(
                f"[QA] {script_path.name}: 총 {total:.1f}s 가 목표 {lo}~{hi}s 밖. "
                f"완주율 위해 조정 고려 (나레이션 줄이기/영어 낭독 제거).",
                file=sys.stderr,
            )

        # 3. 음성을 순서대로 이어 붙인다 (사이에 GAP_SEC 무음)
        gap = work / "gap.mp3"
        _run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", str(GAP_SEC), "-q:a", "9", str(gap)],
        )
        listing = []
        for mp3, _dur, _kind, _text, _hl, _ref in pieces:
            listing.append(f"file '{mp3.name}'")
            listing.append(f"file '{gap.name}'")
        (work / "concat.txt").write_text("\n".join(listing) + "\n", encoding="utf-8")
        _run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
             "-c", "copy", "audio_raw.mp3"],
            cwd=work,
        )
        # 이어 붙인 낭독 전체에 한 번에 마스터링 (길이는 그대로, 음량 일정)
        _run(
            ["ffmpeg", "-y", "-i", "audio_raw.mp3", "-af", VOICE_MASTER,
             "-ar", "44100", "audio.mp3"],
            cwd=work,
        )

        # 4. 배경 + 레터박스 + 자막 + 음성(+배경음악) -> MP4
        #    hook_bg(훅 전용 AI 이미지)가 있으면 그 구간(훅 카드 = segments[0])만
        #    그 이미지로 깔고, 나머지 구간은 기존 bg를 균등분할한다. 훅이 없으면
        #    hook_bg는 무시된다. 훅 카드 길이는 실제 재생 시각(segments[0])을 사용해
        #    나레이션 유무·길이에 따라 자동으로 맞춘다.
        visual_plan = visual_segments(data, pieces, total)
        segs = [(x["media"], x["duration"], x.get("motion", "auto")) for x in visual_plan]
        n_bg = len(segs)

        cmd = ["ffmpeg", "-y"]
        video_parts = []
        for i, (bg, seg_dur, motion) in enumerate(segs):
            src = ROOT / bg
            dst = work / f"bg{i}{src.suffix}"
            shutil.copy(src, dst)
            if is_video(dst):
                cmd += [
                    "-stream_loop", "-1", "-t", f"{seg_dur:.2f}", "-i", dst.name,
                ]
                video_parts.append(
                    f"[{i}:v]setpts=PTS-STARTPTS,"
                    f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},"
                    f"fps={FPS},setsar=1[v{i}]"
                )
            else:
                cmd += [
                    "-framerate", str(FPS), "-loop", "1", "-t", f"{seg_dur:.2f}", "-i", dst.name,
                ]
                video_parts.append(image_motion_filter(i, motion))
        concat_in = "".join(f"[v{i}]" for i in range(n_bg))
        # 레터박스: 템플릿이 지정하면 상하에 검은 바를 깐다 (자막 가독성 + 시네마틱)
        top = layout["letters"]["top"]
        bottom = layout["letters"]["bottom"]
        lb = ""
        if top > 0 or bottom > 0:
            parts = []
            if top > 0:
                parts.append(f"drawbox=x=0:y=0:w={W}:h={top}:color=black@1:t=fill")
            if bottom > 0:
                parts.append(f"drawbox=x=0:y={H-bottom}:w={W}:h={bottom}:color=black@1:t=fill")
            # 각 part는 이미 drawbox= 로 시작하므로 콤마로만 이어 붙인다.
            lb = ",".join(parts) + ","
        video_chain = (
            ";".join(video_parts)
            + f";{concat_in}concat=n={n_bg}:v=1:a=0[vraw];"
            + f"[vraw]{lb}subtitles=sub.ass[vout]"
        )

        cmd += ["-i", "audio.mp3"]
        narration_idx = n_bg

        bgm = data.get("bgm")
        if bgm:
            shutil.copy(ROOT / bgm, work / "bgm.mp3")
            cmd += ["-stream_loop", "-1", "-i", "bgm.mp3"]
            bgm_idx = n_bg + 1
            audio_chain = (
                f"[{bgm_idx}:a]volume={BGM_VOLUME}[bgm];"
                f"[bgm][{narration_idx}:a]sidechaincompress=threshold=0.03:ratio=15:attack=5:release=400[bgm_duck];"
                f"[{narration_idx}:a][bgm_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[amixout];"
                f"[amixout]afade=t=out:st={total-BGM_FADE_SEC:.2f}:d={BGM_FADE_SEC:.2f}[aout]"
            )
            filter_complex = video_chain + ";" + audio_chain
            cmd += ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"]
        else:
            cmd += ["-filter_complex", video_chain, "-map", "[vout]", "-map", f"{narration_idx}:a"]

        tmp_mp4 = work / "out.mp4"
        cmd += ["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-shortest", str(tmp_mp4)]
        subprocess.run(cmd, cwd=work, check=True)
        shutil.move(str(tmp_mp4), str(out_mp4))
        from qa_gate import validate_render
        qa = validate_render(out_mp4)
        print(f"[QA] render PASS: {qa}")
    except Exception:
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
            print(f"FAILED {p.name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()