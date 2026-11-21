"""KJV 쇼츠의 본문·교리·미디어·완성영상 자동 QA 게이트.

대본 사전검사:
- 흠정역/KJV 인용문이 bible/*.json의 해당 절과 정확히 일치하는지 검사
- verse_krv(개역개정) 필드가 있으면 bible/krv_ko.json과 정확히 일치하는지 검사
- 장면 스키마와 미디어 파일 존재 여부 검사
- 채널 교리와 충돌하는 금지 표현 차단

렌더 사후검사:
- MP4 해상도·코덱·길이·오디오 스트림 검사
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
REF_RE = re.compile(r"^(.+?)\s+(\d+):(\d+)$")

# 사랑침례교회/KJVO·세대주의·환난 전 휴거 기준에서 자동 발행하면 안 되는 주장.
HARD_BLOCK = {
    "재림 날짜 단정": re.compile(r"(?:예수님|그리스도|주님).{0,12}(?:재림|돌아오).{0,16}(?:20\d{2}년|\d{1,2}월\s*\d{1,2}일)"),
    "대체신학": re.compile(r"교회가\s*(?:새로운\s*)?이스라엘을\s*(?:완전히\s*)?(?:대체|대신)"),
    "외경적 예언": re.compile(r"노스트라다무스|파티마\s*예언|채널링"),
    "적그리스도 인물 단정": re.compile(r"(?:적그리스도는|적그리스도가)\s*[가-힣A-Za-z· ]{2,30}(?:이다|입니다)"),
}

ALLOWED_MOTION = {"auto", "zoom_in", "zoom_out", "pan_left", "pan_right", "none"}


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _verse_blocks(data: dict) -> list[dict]:
    if data.get("verses") is not None:
        return data["verses"]
    return [{k: data.get(k) for k in ("ref", "verse_ko", "verse_en", "verse_krv", "narration", "scenes")}]


def _bible_indexes() -> tuple[dict, dict, dict]:
    ko = _load_json(ROOT / "bible" / "kjv_ko.json")
    krv = _load_json(ROOT / "bible" / "krv_ko.json")  # 개역개정 © 대한성서공회 — 로컬 검증 전용
    en_raw = _load_json(ROOT / "bible" / "kjv_en.json")
    en_books = en_raw.get("books", [])
    # 두 DB 모두 정경 66권 순서다. 영어 책 이름 표기 차이를 별도 수기 매핑하지 않고
    # 정경 순서로 연결해 오타 가능성을 줄인다.
    if len(ko) != len(en_books) or len(krv) != len(ko):
        raise ValueError(f"성경 DB 권수 불일치: KO={len(ko)}, EN={len(en_books)}, KRV={len(krv)}")
    en_by_ko = {}
    for ko_name, en_book in zip(ko.keys(), en_books):
        chapters = {}
        for chapter in en_book.get("chapters", []):
            verses = {str(v["verse"]): v["text"] for v in chapter.get("verses", [])}
            chapters[str(chapter["chapter"])] = verses
        en_by_ko[ko_name] = chapters
    return ko, en_by_ko, krv


def _exact_verse(db: dict, ref: str) -> str | None:
    m = REF_RE.match(ref or "")
    if not m:
        return None
    book, chapter, verse = m.groups()
    return db.get(book, {}).get(chapter, {}).get(verse)


def _all_text(data: dict) -> str:
    chunks = [str(data.get(k, "")) for k in ("topic", "hook", "hook_voice", "outro", "outro_voice")]
    for block in _verse_blocks(data):
        chunks.extend(str(x) for x in block.get("narration", []) or [])
        chunks.extend(str(s.get("narration", "")) for s in block.get("scenes", []) or [])
    return "\n".join(chunks)


def validate_script_data(data: dict, script_path: Path | None = None) -> list[str]:
    """문제가 있으면 ValueError/FileNotFoundError를 발생시키고 경고 목록을 반환."""
    label = script_path.name if script_path else "script"
    blocks = _verse_blocks(data)
    if not blocks:
        raise ValueError(f"{label}: verses가 비어 있음")

    ko_db, en_db, krv_db = _bible_indexes()
    for i, block in enumerate(blocks):
        ref = block.get("ref")
        expected_ko = _exact_verse(ko_db, ref)
        expected_en = _exact_verse(en_db, ref)
        if expected_ko is None or expected_en is None:
            raise ValueError(f"{label}: verses[{i}] DB에서 찾을 수 없는 주소: {ref}")
        if block.get("verse_ko") != expected_ko:
            raise ValueError(f"{label}: {ref} 흠정역 본문이 kjv_ko.json과 불일치")
        if block.get("verse_en") != expected_en:
            raise ValueError(f"{label}: {ref} KJV 본문이 kjv_en.json과 불일치")
        if block.get("verse_krv") is not None:
            # 개역개정 인용 검증 (© 대한성서공회 — 게이트는 로컬에서만 동작)
            expected_krv = _exact_verse(krv_db, ref)
            if expected_krv is None:
                raise ValueError(f"{label}: {ref} 개역개정(krv_ko.json)에서 찾을 수 없는 주소")
            if block.get("verse_krv") != expected_krv:
                raise ValueError(f"{label}: {ref} 개역개정 본문이 krv_ko.json과 불일치")

        scenes = block.get("scenes")
        narration = block.get("narration")
        if scenes is not None:
            if not isinstance(scenes, list) or not scenes:
                raise ValueError(f"{label}: verses[{i}].scenes는 비어 있지 않은 배열이어야 함")
            for j, scene in enumerate(scenes):
                if not isinstance(scene, dict):
                    raise ValueError(f"{label}: scenes[{j}]는 객체여야 함")
                if not str(scene.get("narration", "")).strip():
                    raise ValueError(f"{label}: scenes[{j}].narration 누락")
                media = scene.get("media")
                if not media:
                    raise ValueError(f"{label}: scenes[{j}].media 누락")
                if not (ROOT / media).exists():
                    raise FileNotFoundError(f"{label}: scenes[{j}] 미디어 없음: {media}")
                motion = scene.get("motion", "auto")
                if motion not in ALLOWED_MOTION:
                    raise ValueError(f"{label}: scenes[{j}].motion={motion!r} 지원 안 함")
        elif not isinstance(narration, list) or not narration:
            raise ValueError(f"{label}: verses[{i}]에 narration 또는 scenes 필요")

    text = _all_text(data)
    for reason, pattern in HARD_BLOCK.items():
        hit = pattern.search(text)
        if hit:
            raise ValueError(f"{label}: 교리 안전 게이트 차단({reason}): {hit.group(0)!r}")

    # 모든 참조 미디어를 사전에 확인한다.
    media_paths: list[str] = []
    bg = data.get("bg", [])
    media_paths.extend([bg] if isinstance(bg, str) else list(bg))
    if data.get("hook_bg"):
        media_paths.append(data["hook_bg"])
    if data.get("outro_bg"):
        media_paths.append(data["outro_bg"])
    if data.get("bgm"):
        media_paths.append(data["bgm"])
    missing = [p for p in media_paths if p and not (ROOT / p).exists()]
    if missing:
        raise FileNotFoundError(f"{label}: 미디어 없음: {missing}")

    warnings = []
    scene_count = sum(len(b.get("scenes", []) or []) for b in blocks)
    if scene_count and scene_count < 5:
        warnings.append(f"장면이 {scene_count}개뿐이라 시각 리듬이 단조로울 수 있음")
    return warnings


# ---- 대본 문장 품질 게이트 (대본 작성 규칙 v2, 크론 사전 QA에서만 적용) ----
MAX_SPOKEN_CHARS = 320   # 훅+본문낭독+해설+아웃트로 글자수. 실측 5.8자/초 → 약 55초
MAX_SENTENCE = 40        # 해설 한 문장 최대 글자수
MAX_HOOK = 24            # 화면 훅 최대 글자수
MAX_HOOK_VOICE = 60
MAX_FORMAL_RUN = 2       # "~니다"로 끝나는 문장이 연속 몇 개까지 허용되는가
CLICHES = re.compile(
    r"무엇이\s*(?:달라진|사라진|바뀐)\s*걸까요|살펴보겠습니다|알아보겠습니다|"
    r"정확한 본문을 더 알고 싶|주목해야\s*합니다|중요한 차이가 있습니다"
)
EMPTY_KRV = ("", "(없음)", "없음")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+", text or "") if s.strip()]


def style_issues(data: dict) -> list[str]:
    """대본 작성 규칙 v2 위반 목록. 비어 있으면 통과."""
    issues: list[str] = []
    blocks = _verse_blocks(data)
    narr: list[str] = []
    spoken = len(data.get("hook_voice", "")) + len(data.get("outro_voice", ""))
    for i, b in enumerate(blocks):
        ref = b.get("ref")
        krv = b.get("verse_krv")
        if krv is None:
            issues.append(f"{ref}: verse_krv 누락 → 비교 카드가 안 나온다 (krv_ko.json에서 코드로 추출)")
            krv = ""
        hls = b.get("highlight") or []
        ko = b.get("verse_ko", "")
        stray = [h for h in hls if h not in ko and h not in krv]
        if stray:
            issues.append(f"{ref}: highlight가 본문에 없음 {stray} → 흠정역/개역개정 본문 속 문구만 쓴다")
        if not any(h in ko for h in hls):
            issues.append(f"{ref}: 흠정역 본문 속 highlight 문구가 하나도 없음")
        if krv.strip() not in EMPTY_KRV and not any(h in krv for h in hls):
            issues.append(f"{ref}: 개역개정 본문 속 highlight 문구가 하나도 없음")
        spoken += len(ko)
        lines = [s.get("narration", "") for s in b.get("scenes") or []] or list(b.get("narration") or [])
        narr.extend(lines)
    spoken += sum(len(s) for s in narr)
    if spoken > MAX_SPOKEN_CHARS:
        issues.append(f"낭독 총 {spoken}자 > {MAX_SPOKEN_CHARS}자 (약 {spoken / 5.8:.0f}초) → 해설을 줄이거나 보조 구절을 빼라")
    long = [s for s in narr if len(s) > MAX_SENTENCE]
    if long:
        issues.append(f"해설 문장이 {MAX_SENTENCE}자 초과: {long}")
    if len(data.get("hook", "")) > MAX_HOOK:
        issues.append(f"화면 훅 {len(data['hook'])}자 > {MAX_HOOK}자")
    if len(data.get("hook_voice", "")) > MAX_HOOK_VOICE:
        issues.append(f"hook_voice {len(data['hook_voice'])}자 > {MAX_HOOK_VOICE}자")
    flow = _sentences(data.get("hook_voice", "")) + [x for s in narr for x in _sentences(s)] \
        + _sentences(data.get("outro_voice", ""))
    run = 0
    for s in flow:
        run = run + 1 if re.search(r"니다[.!]?$", s) else 0
        if run > MAX_FORMAL_RUN:
            issues.append(f"'~니다' 문장이 {run}번 연속: {s!r} → 구어체·질문·짧은 명사문을 섞어라")
            break
    text = "\n".join(flow + [data.get("hook", ""), data.get("outro", "")])
    for m in CLICHES.finditer(text):
        issues.append(f"상투 문구 금지: {m.group(0)!r}")
    outro = data.get("outro", "") + data.get("outro_voice", "")
    if outro and not re.search(r"구독|댓글", outro):
        issues.append("아웃트로에 구독 또는 댓글 유도가 없음")
    return issues


def validate_script_file(path: Path, style: bool = False) -> list[str]:
    data = _load_json(path)
    warnings = validate_script_data(data, path)
    if style:
        issues = style_issues(data)
        if issues:
            raise ValueError(f"{path.name}: 대본 작성 규칙 v2 위반\n- " + "\n- ".join(issues))
    return warnings


def probe_video(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=index,codec_type,codec_name,width,height",
        "-of", "json", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def validate_render(path: Path, max_duration: float = 90.0) -> dict:
    if not path.exists() or path.stat().st_size < 100_000:
        raise ValueError(f"완성영상이 없거나 비정상적으로 작음: {path}")
    info = probe_video(path)
    duration = float(info.get("format", {}).get("duration", 0))
    videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    audios = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if len(videos) != 1 or not audios:
        raise ValueError(f"영상/오디오 스트림 이상: video={len(videos)}, audio={len(audios)}")
    v = videos[0]
    if (v.get("width"), v.get("height")) != (1080, 1920):
        raise ValueError(f"세로 해상도 불일치: {v.get('width')}x{v.get('height')}")
    if v.get("codec_name") != "h264":
        raise ValueError(f"비디오 코덱 불일치: {v.get('codec_name')}")
    if not (10.0 <= duration <= max_duration):
        raise ValueError(f"쇼츠 길이 범위 이탈: {duration:.2f}s (허용 10~{max_duration}s)")
    return {"duration": duration, "width": v["width"], "height": v["height"], "video_codec": v["codec_name"], "audio_codec": audios[0].get("codec_name")}


if __name__ == "__main__":
    import sys
    script = Path(sys.argv[1])
    # 사전 QA(인자 1개)일 때만 문장 품질 게이트를 건다. 사후 QA는 이미 통과한 대본.
    warnings = validate_script_file(script, style=len(sys.argv) == 2)
    print(f"PRE-QA PASS: {script.name}" + (f" | warnings={warnings}" if warnings else ""))
    if len(sys.argv) > 2:
        print("POST-QA PASS:", validate_render(Path(sys.argv[2])))
