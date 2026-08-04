"""build.py의 순수 함수만 테스트한다 (ffmpeg/네트워크 불필요).

ass_time과 segment_timings은 자막이 실제 오디오 위의 정확한 시각에
겹치는지를 결정하는 계산이다. 여기가 틀리면 화면의 말과 소리의 말이
어긋난 채로 영상이 나간다.

write_ass는 파일을 쓰므로 순수 함수는 아니지만, 페이드 태그가 매 줄에
실제로 붙는지는 파일을 열어보지 않으면 확인할 수 없어 함께 테스트한다.
"""
from pathlib import Path

import pytest

from build import GAP_SEC, SUB_FADE_MS, ass_time, segment_timings, write_ass


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
