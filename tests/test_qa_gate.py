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


def _v2(**over):
    d = {
        "hook": "예수님의 질문이 바뀌었다",
        "hook_voice": "예수님이 하신 질문, 성경마다 다르게 적혀 있어요.",
        "verses": [{"ref": "마태복음 19:17", "verse_ko": "네가 어찌하여 나를 선하다 하느냐?",
                    "verse_krv": "어찌하여 선한 일을 내게 묻느냐",
                    "highlight": ["나를 선하다 하느냐", "선한 일을 내게 묻느냐"],
                    "narration": ["개역개정은 이렇게 옮겼어요.", "흠정역은 다릅니다.", "셈이죠."]}],
        "outro": "댓글로 알려 주세요", "outro_voice": "댓글로 알려 주세요.",
    }
    d.update(over)
    return d


def test_style_v2_passes_and_blocks():
    from qa_gate import style_issues
    assert style_issues(_v2()) == []
    bad = _v2(hook="무엇이 달라진 걸까요 아주아주 긴 훅 문구입니다 정말로", outro="끝", outro_voice="끝.")
    bad["verses"][0]["highlight"] = ["그대로 남아 있습니다"]
    bad["verses"][0]["narration"] = ["하나입니다.", "둘입니다.", "셋입니다."]
    msgs = "\n".join(style_issues(bad))
    for key in ("본문에 없음", "화면 훅", "3번 연속", "상투 문구", "구독 또는 댓글"):
        assert key in msgs, key
