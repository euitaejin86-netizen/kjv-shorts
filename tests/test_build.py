"""build.py의 순수 함수만 테스트한다 (ffmpeg/네트워크 불필요).

ass_time과 segment_timings은 자막이 실제 오디오 위의 정확한 시각에
겹치는지를 결정하는 계산이다. 여기가 틀리면 화면의 말과 소리의 말이
어긋난 채로 영상이 나간다.
"""
from pathlib import Path

import pytest

from build import GAP_SEC, ass_time, segment_timings


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
