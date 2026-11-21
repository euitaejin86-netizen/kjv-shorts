import pytest

from make_script import make, published

BIBLE = (
    {"요한복음": {"6": {"47": "KO"}, "3": {"16": "KO316"}}},
    {"요한복음": {"6": {"47": "EN"}, "3": {"16": "EN316"}}},
    {"요한복음": {"6": {"47": "KRV"}, "3": {"16": "KRV316"}}},
)
DRAFT = {"topic_short": "주제", "hook": "훅", "hook_voice": "훅 낭독",
         "verses": [{"ref": "요한복음 3:16", "highlight": ["x"], "narration": ["문장."]}],
         "outro": "댓글", "outro_voice": "구독"}
PROGRESS = """| # | 구절 | 주제 |
|---|------|------|
| 32 | 로마서 8:1 | a | ok |
|| 33 | 요한복음 6:47 | b | ok |
"""


def test_published_parses_rows_even_with_broken_pipes():
    assert published(PROGRESS) == {32: "로마서 8:1", 33: "요한복음 6:47"}


def test_make_fills_verses_from_db_and_numbers_next():
    nn, d = make(DRAFT, published(PROGRESS), BIBLE)
    assert nn == 34
    v = d["verses"][0]
    assert (v["verse_ko"], v["verse_en"], v["verse_krv"]) == ("KO316", "EN316", "KRV316")
    assert d["topic"] == "개역 vs 흠정역 #34 · 요한복음 3:16 — 주제"
    assert d["template"] == "자극형" and "topic_short" not in d


def test_make_blocks_already_published_ref():
    draft = {**DRAFT, "verses": [{"ref": "요한복음 6:47", "narration": ["a."]}]}
    with pytest.raises(ValueError, match="#33"):
        make(draft, published(PROGRESS), BIBLE)


def test_make_blocks_unknown_ref():
    draft = {**DRAFT, "verses": [{"ref": "요한복음 9:99", "narration": ["a."]}]}
    with pytest.raises(KeyError):
        make(draft, published(PROGRESS), BIBLE)
