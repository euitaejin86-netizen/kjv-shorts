"""build.py의 순수 함수만 테스트한다 (ffmpeg/네트워크 불필요).

ass_time과 segment_timings은 자막이 실제 오디오 위의 정확한 시각에
겹치는지를 결정하는 계산이다. 여기가 틀리면 화면의 말과 소리의 말이
어긋난 채로 영상이 나간다.

write_ass는 파일을 쓰므로 순수 함수는 아니지만, 페이드 태그가 매 줄에
실제로 붙는지는 파일을 열어보지 않으면 확인할 수 없어 함께 테스트한다.
"""
from pathlib import Path

import pytest

from build import (
    GAP_SEC,
    SUB_FADE_MS,
    ass_time,
    bg_list,
    bg_segment_durations,
    ref_display,
    segment_timings,
    write_ass,
)


def test_ass_time_formats_zero():
    assert ass_time(0) == "0:00:00.00"


def test_ass_time_formats_minutes_and_seconds():
    assert ass_time(65.5) == "0:01:05.50"


def test_ass_time_formats_hours():
    assert ass_time(3661.25) == "1:01:01.25"


def test_ass_time_clamps_negative_to_zero():
    assert ass_time(-1.0) == "0:00:00.00"


def test_segment_timings_chains_with_gap():
    pieces = [
        (Path("a.mp3"), 2.0, "one"),
        (Path("b.mp3"), 3.0, "two"),
        (Path("c.mp3"), 1.5, "three"),
    ]
    segments, total = segment_timings(pieces, gap=0.4)
    assert segments == [
        (0.0, 2.0, "one"),
        (2.4, 5.4, "two"),
        (5.8, 7.3, "three"),
    ]
    assert total == pytest.approx(7.7)  # 마지막 조각 뒤에도 gap이 더해진다


def test_segment_timings_empty_pieces():
    segments, total = segment_timings([], gap=GAP_SEC)
    assert segments == []
    assert total == 0.0


def test_segment_timings_default_gap_matches_module_constant():
    pieces = [(Path("a.mp3"), 1.0, "x"), (Path("b.mp3"), 1.0, "y")]
    segments, _total = segment_timings(pieces)
    assert segments[1][0] == 1.0 + GAP_SEC


def test_write_ass_fades_every_line(tmp_path):
    segments = [(0.0, 2.0, "one"), (2.4, 5.4, "two")]
    out = tmp_path / "sub.ass"
    write_ass(segments, out)
    text = out.read_text(encoding="utf-8")
    dialogue_lines = [l for l in text.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogue_lines) == 2

    fade_tag = f"{{\\fad({SUB_FADE_MS},{SUB_FADE_MS})}}"
    # 페이드 태그는 텍스트 필드 맨 앞에 와야 한다 (ASS override 태그는 등장한
    # 지점부터 적용되므로, 텍스트 뒤에 붙으면 아무 효과가 없다).
    assert f",{fade_tag}one" in dialogue_lines[0]
    assert f",{fade_tag}two" in dialogue_lines[1]


def test_bg_list_normalizes_single_string():
    assert bg_list({"bg": "bg/plain.jpg"}) == ["bg/plain.jpg"]


def test_bg_list_passes_through_list():
    assert bg_list({"bg": ["bg/a.jpg", "bg/b.jpg"]}) == ["bg/a.jpg", "bg/b.jpg"]


def test_bg_segment_durations_splits_evenly():
    # 정확히 나눠떨어지는 경우: 세 조각이 완전히 동일해야 한다
    assert bg_segment_durations(9.0, 3) == pytest.approx([3.0, 3.0, 3.0])


def test_bg_segment_durations_last_segment_absorbs_remainder():
    # 82.83 / 3 은 딱 떨어지지 않는다. 반올림 오차가 마지막 조각에 몰려야
    # 앞쪽 조각들이 흔들리지 않고, 합계가 total과 정확히 같아야 영상 끝에
    # 검은 프레임이나 조기 컷이 생기지 않는다.
    durations = bg_segment_durations(82.83, 3)
    assert len(durations) == 3
    assert durations[0] == durations[1]
    assert sum(durations) == pytest.approx(82.83)


def test_bg_segment_durations_single_image_gets_full_duration():
    assert bg_segment_durations(50.0, 1) == pytest.approx([50.0])


def test_bg_segment_durations_rejects_zero_images():
    with pytest.raises(ValueError):
        bg_segment_durations(50.0, 0)


def test_ref_display_converts_colon_to_hangul_counters():
    assert ref_display("창세기 3:24") == "창세기 3장 24절"


def test_ref_display_handles_multi_word_book_names():
    assert ref_display("데살로니가전서 4:17") == "데살로니가전서 4장 17절"


def test_ref_display_returns_original_on_unexpected_format():
    # 형식이 예상과 다르면(콜론이 없는 등) 원문을 그대로 돌려주고 조용히 실패하지 않는다.
    assert ref_display("서문") == "서문"
