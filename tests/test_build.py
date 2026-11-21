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
    load_layout,
    ref_display,
    segment_timings,
    scene_list,
    visual_segments,
    write_ass,
)


def _layout():
    return load_layout({})  # template/style 없는 기본 레이아웃


def _piece(name, dur, kind="hook", text="hello", hl=None, ref=""):
    # (mp3, 재생길이, kind, 자막 raw, highlight, ref) 6튜플 (작성 x 종류를 감쌈)
    return (Path(name), dur, kind, text, hl or [], ref)


def _seg(start, end, kind="hook", text="hello", hl=None, ref=""):
    return (start, end, kind, text, hl or [], ref)


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
        _piece("a.mp3", 2.0, text="one"),
        _piece("b.mp3", 3.0, text="two"),
        _piece("c.mp3", 1.5, text="three"),
    ]
    segments, total = segment_timings(pieces, gap=0.4)
    assert segments == [
        _seg(0.0, 2.0, text="one"),
        _seg(2.4, 5.4, text="two"),
        _seg(5.8, 7.3, text="three"),
    ]
    assert total == pytest.approx(7.7)  # 마지막 조각 뒤에도 gap이 더해진다


def test_segment_timings_empty_pieces():
    segments, total = segment_timings([], gap=GAP_SEC)
    assert segments == []
    assert total == 0.0


def test_segment_timings_default_gap_matches_module_constant():
    pieces = [_piece("a.mp3", 1.0), _piece("b.mp3", 1.0)]
    segments, _total = segment_timings(pieces)
    assert segments[1][0] == 1.0 + GAP_SEC


def test_write_ass_fades_every_line(tmp_path):
    segments = [_seg(0.0, 2.0, text="one"), _seg(2.4, 5.4, text="two")]
    out = tmp_path / "sub.ass"
    write_ass(segments, out, _layout())
    text = out.read_text(encoding="utf-8")
    dialogue_lines = [l for l in text.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogue_lines) == 2

    fade_tag = f"{{\\fad({SUB_FADE_MS},{SUB_FADE_MS})}}"
    # ASS Dialogue 형식: Layer,Start,End,Style,Name,ML,MR,MV,Effect,Text (10 필드).
    # Text는 split(",", 9) 로 정확히 분리된다. fade 태그 자체에 콤마
    # (fad(200,400))가 있어서, 콤마로 그냥 자르면 fade가 갈린다.
    for i, line in enumerate(dialogue_lines):
        text_field = line.split(",", 9)[9]
        assert text_field.startswith(fade_tag), f"line {i} fade not first: {text_field!r}"
    # 본문 텍스트가 들어 있는지도 확인한다 (색 태그에 가려져 사라지지 않았는지)
    assert "one" in dialogue_lines[0]
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


def test_scene_list_flattens_multiverse_scenes():
    data = {"verses": [
        {"scenes": [{"narration": "a", "media": "a.mp4"}]},
        {"scenes": [{"narration": "b", "media": "b.mp4"}]},
    ]}
    assert [s["media"] for s in scene_list(data)] == ["a.mp4", "b.mp4"]


def test_visual_segments_tracks_tts_piece_durations():
    data = {
        "hook": "hook", "hook_bg": "hook.png", "outro": "out",
        "verses": [{"scenes": [
            {"narration": "one", "media": "one.mp4", "motion": "none"},
            {"narration": "two", "media": "two.mp4", "motion": "auto"},
        ]}],
    }
    pieces = [
        _piece("h.mp3", 2.0), _piece("v.mp3", 3.0),
        _piece("1.mp3", 4.0), _piece("2.mp3", 5.0), _piece("o.mp3", 2.5),
    ]
    total = sum(p[1] + GAP_SEC for p in pieces)
    plan = visual_segments(data, pieces, total=total)
    assert [p["media"] for p in plan] == ["hook.png", "one.mp4", "one.mp4", "two.mp4", "two.mp4"]
    assert [p["duration"] for p in plan] == pytest.approx([2.4, 3.4, 4.4, 5.4, 2.9])


def test_ref_display_converts_colon_to_hangul_counters():
    assert ref_display("창세기 3:24") == "창세기 3장 24절"


def test_ref_display_handles_multi_word_book_names():
    assert ref_display("데살로니가전서 4:17") == "데살로니가전서 4장 17절"


def test_ref_display_returns_original_on_unexpected_format():
    # 형식이 예상과 다르면(콜론이 없는 등) 원문을 그대로 돌려주고 조용히 실패하지 않는다.
    assert ref_display("서문") == "서문"





def test_excerpt_keeps_phrase_with_attached_punct():
    from build import excerpt
    v = "그분께서 그에게 이르시되, 네가 어찌하여 나를 선하다 하느냐? 한 분 곧 하나님 외에는"
    pre, ph, post = excerpt(v, "나를 선하다 하느냐")
    assert (pre, ph, post) == ("… 네가 어찌하여 ", "나를 선하다 하느냐", "?…")
    assert excerpt("가 나 다", "없는문구") == ("가 나 다", "", "")


def test_compare_card_missing_verse():
    from build import compare_card, WHITE, GOLD, SILVER
    col = {"white": WHITE, "gold": GOLD, "silver": SILVER}
    blk = {"verse_ko": "사람의 아들은 잃어버린 것을 구원하려고 왔느니라.",
           "verse_krv": "(없음)", "highlight": ["잃어버린 것을 구원하려고"]}
    text, h = compare_card(blk, "마태복음 18장 11절", col)
    assert "( 없음 )" in text and h > 0
    assert "{\c%s}잃어버린" % GOLD in text  # 줄이 나뉘어도 강조 시작
