import json
from pathlib import Path

import pytest

from qa_gate import validate_script_data


ROOT = Path(__file__).parents[1]


def _valid():
    return json.loads((ROOT / "scripts" / "2026-08-18-krv-vs-kjb-04.json").read_text(encoding="utf-8"))


def test_qa_accepts_verified_existing_script():
    assert validate_script_data(_valid()) == []


def test_qa_blocks_modified_korean_verse():
    data = _valid()
    data["verses"][0]["verse_ko"] += " 오타"
    with pytest.raises(ValueError, match="흠정역 본문"):
        validate_script_data(data)


def test_qa_blocks_modified_english_verse():
    data = _valid()
    data["verses"][0]["verse_en"] += " typo"
    with pytest.raises(ValueError, match="KJV 본문"):
        validate_script_data(data)


def test_qa_blocks_doctrine_conflict():
    data = _valid()
    data["verses"][0]["narration"].append("교회가 이스라엘을 완전히 대체합니다.")
    with pytest.raises(ValueError, match="교리 안전 게이트"):
        validate_script_data(data)


# ---- 개역개정(verse_krv) 검증 게이트 ----
def _with_krv(data, ref):
    from qa_gate import _bible_indexes, _exact_verse
    ko, en, krv = _bible_indexes()
    block = data["verses"][0]
    block["ref"] = ref
    block["verse_ko"] = _exact_verse(ko, ref)
    block["verse_en"] = _exact_verse(en, ref)
    block["verse_krv"] = _exact_verse(krv, ref)
    return data


def test_qa_accepts_matching_krv_verse():
    data = _with_krv(_valid(), "빌립보서 2:6")
    assert validate_script_data(data) == []


def test_qa_blocks_tampered_krv_verse():
    data = _with_krv(_valid(), "빌립보서 2:6")
    data["verses"][0]["verse_krv"] = data["verses"][0]["verse_krv"].replace("본체", "본질")
    with pytest.raises(ValueError, match="개역개정 본문"):
        validate_script_data(data)


def test_qa_blocks_krv_for_missing_ref():
    data = _with_krv(_valid(), "요한계시록 12:18")  # 개역개정 공식판에 없는 절
    with pytest.raises(ValueError, match="찾을 수 없는 주소"):
        validate_script_data(data)
