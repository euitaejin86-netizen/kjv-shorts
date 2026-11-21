# -*- coding: utf-8 -*-
"""초안 JSON → '개역 vs 흠정역' 기본 대본. 크론이 매번 genNN.py를 새로 쓰지 않게 한다.

초안에는 사람이 쓰는 글(topic·hook·narration·outro 등)과 구절 주소(ref)만 넣는다.
본문(verse_ko/verse_en/verse_krv)은 여기서 bible/*.json으로 채운다 — 손입력 금지 규칙을 코드로 강제.
다음 번호는 진행도 표의 마지막 #N + 1, 이미 공개한 구절이면 중단한다.

usage: python make_script.py draft.json [YYYY-MM-DD]
초안 예: {"topic_short": "...", "hook": "...", "hook_voice": "...", "hook_hl": [...],
          "verses": [{"ref": "요한복음 6:47", "highlight": [...], "narration": [...]}],
          "outro": "...", "outro_voice": "..."}
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from qa_gate import REF_RE, _bible_indexes, _exact_verse

ROOT = Path(__file__).parent
PROGRESS = Path(r"C:\Users\uieta\Obsidian\Second\wiki\faith\KJV-시리즈-진행도.md")
DEFAULTS = {
    "template": "자극형",
    "hook_bg": "bg/hook_missing_verse.png",
    "bg": ["bg/video/bible_open.mp4", "bg/video/sunrays_window.mp4",
           "bg/video/candle_serene.mp4", "bg/video/clouds_light.mp4"],
    "bgm": "bgm/Prelude No. 12 - Chris Zabriskie.mp3",
}
REQUIRED = ("topic_short", "hook", "hook_voice", "verses", "outro", "outro_voice")


def published(progress_text: str) -> dict[int, str]:
    """진행도 표에서 {번호: 구절 주소}. 표 줄은 '| 33 | 요한복음 6:47 | ...' 꼴."""
    rows = {}
    for line in progress_text.splitlines():
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 2 and cells[0].isdigit():
            rows[int(cells[0])] = cells[1]
    return rows


def make(draft: dict, rows: dict[int, str], bible: tuple[dict, dict, dict]) -> tuple[int, dict]:
    missing = [k for k in REQUIRED if not draft.get(k)]
    if missing:
        raise ValueError(f"초안 필드 누락: {missing}")
    ko, en, krv = bible
    used = set(rows.values())
    nn = max(rows, default=0) + 1
    verses = []
    for b in draft["verses"]:
        ref = b["ref"]
        if not REF_RE.match(ref):
            raise ValueError(f"구절 주소 형식 오류: {ref!r} (예: '요한복음 6:47')")
        if ref in used:
            num = next(n for n, r in rows.items() if r == ref)
            raise ValueError(f"{ref}는 이미 #{num}에서 공개했다 — 다른 구절을 골라라")
        texts = [_exact_verse(db, ref) for db in (ko, en, krv)]
        if None in texts:
            raise KeyError(f"성경 DB에 없는 구절: {ref}")
        verses.append({"ref": ref, "verse_ko": texts[0], "verse_en": texts[1], "verse_krv": texts[2],
                       "highlight": b.get("highlight", []), "narration": b["narration"]})
    first = verses[0]["ref"]
    data = {**DEFAULTS, **{k: v for k, v in draft.items() if k not in ("topic_short", "verses")}}
    data.update(topic=f"개역 vs 흠정역 #{nn} · {first} — {draft['topic_short']}", ref=first, verses=verses)
    return nn, data


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    draft = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    day = sys.argv[2] if len(sys.argv) > 2 else dt.date.today().isoformat()
    nn, data = make(draft, published(PROGRESS.read_text(encoding="utf-8")), _bible_indexes())
    out = ROOT / "scripts" / f"{day}-krv-vs-kjb-{nn:02d}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {out.relative_to(ROOT)}  (#{nn})")


if __name__ == "__main__":
    main()
