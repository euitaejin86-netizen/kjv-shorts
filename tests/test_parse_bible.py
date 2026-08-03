import fitz
import pytest

from parse_bible import BIBLE_PDF, classify_lines


@pytest.fixture(scope="module")
def doc():
    return fitz.open(BIBLE_PDF)


def test_drops_page_number_and_running_header(doc):
    # 페이지 30은 상단에 "13"(페이지 번호)과 "창세기 12"(러닝 헤더)를 갖는다.
    texts = [l.text for l in classify_lines(doc[30])]
    assert "13" not in texts
    assert "창세기 12" not in texts


def test_marks_verse_starts(doc):
    # 페이지 30 좌단은 창세기 11:8로 시작한다.
    starts = [l.verse_no for l in classify_lines(doc[30]) if l.verse_no is not None]
    assert starts[:4] == [8, 9, 10, 11]


def test_continuation_lines_have_no_verse_no(doc):
    # 첫 줄은 앞 페이지에서 넘어온 이어지는 줄이다.
    assert classify_lines(doc[30])[0].verse_no is None


def test_drops_chapter_heading(doc):
    # 20쪽에는 크기 12.5의 "제 2 장" 장 제목이 있다. 본문에 섞이면
    # 앞 절 끝에 붙어 조용히 오염된다. 절 수는 그대로라 검증도 통과한다.
    texts = [l.text for l in classify_lines(doc[20])]
    assert not any("제" in t and "장" in t and len(t) < 10 for t in texts)


def test_drops_psalm_chapter_heading_and_superscription(doc):
    # 시편은 "제 18 편"(크기 12.5)을 쓰고, 그 아래 표제(크기 10.3)가 온다.
    # KJV는 표제에 절 번호를 매기지 않으므로 표제도 버려야 절 수가 맞는다.
    texts = [l.text for l in classify_lines(doc[719])]
    assert not any("제 18 편" == t for t in texts)
    assert not any("악장에게 준" in t for t in texts)


def test_drops_editor_section_headings(doc):
    # 1550쪽(요한의 둘째 서신)에는 "진리 안에서 걸으라" 소제목이 있다.
    texts = [l.text for l in classify_lines(doc[1550])]
    assert "진리 안에서 걸으라" not in texts


def test_drops_book_title_and_intro_block(doc):
    # 권 시작 페이지의 제목 줄과 소개 블록이 남으면 앞 절에 붙는다.
    texts = " ".join(l.text for l in classify_lines(doc[18]))
    assert "기록자:" not in texts
    assert "모세의 첫째 책" not in texts


def test_genesis_1_1_is_clean(doc):
    # 18쪽 좌단 첫 절이 창세기 1:1이다.
    lines = classify_lines(doc[18])
    first = next(l for l in lines if l.verse_no == 1)
    assert first.text.startswith("처음에 하나님께서")


def test_two_column_reading_order(doc):
    # 좌단을 모두 읽은 뒤 우단으로 넘어가야 절 번호가 단조 증가한다.
    starts = [l.verse_no for l in classify_lines(doc[1550]) if l.verse_no is not None]
    assert starts == sorted(starts)


def test_drops_numbered_list_items_not_verse_starts(doc):
    # 1578쪽은 부록 목차로 "1. 킹제임스 성경과 틴데일" 같은 번호 목록이
    # 절 시작과 같은 크기(12.18)로 찍혀 있다. 숫자 뒤에 마침표가 오는
    # 목록 항목은 절 시작("1 text", "1 ¶ text")과 형태가 다르므로
    # 절 번호로 잡히면 안 된다.
    starts = [l.verse_no for l in classify_lines(doc[1578]) if l.verse_no is not None]
    assert starts == []


import re

from parse_bible import BOOKS_KO, build_bible, load_expected_structure


def test_books_ko_is_the_canon():
    assert len(BOOKS_KO) == 66
    assert BOOKS_KO[0] == "창세기"
    assert BOOKS_KO[38] == "말라기"   # 구약 마지막
    assert BOOKS_KO[39] == "마태복음"  # 신약 첫 권
    assert BOOKS_KO[-1] == "요한계시록"
    assert len(set(BOOKS_KO)) == 66   # 중복 없음


def test_expected_structure_matches_known_kjv_totals():
    expected = load_expected_structure()
    assert len(expected) == 66
    assert sum(sum(ch.values()) for ch in expected) == 31102
    assert sum(expected[0].values()) == 1533  # 창세기


def test_build_bible_matches_english_structure():
    bible = build_bible()  # 구조가 어긋나면 예외를 던진다
    assert len(bible) == 66
    total = sum(len(v) for ch in bible.values() for v in ch.values())
    assert total == 31102
    assert bible["창세기"]["1"]["1"].startswith("처음에 하나님께서")
    assert "믿음은" in bible["히브리서"]["11"]["1"]
    assert all(v.strip() for ch in bible.values() for vs in ch.values() for v in vs.values())


def test_no_chapter_heading_leaked_into_verses():
    # 장 제목이 앞 절 끝에 붙는 오염은 절 수 검증을 통과해 버린다.
    # 각 권 마지막 장 마지막 절을 훑어 "제 N 장"/"제 N 편" 잔재를 잡는다.
    bible = build_bible()
    leaked = [
        f"{book} {ch}:{v}"
        for book, chapters in bible.items()
        for ch, verses in chapters.items()
        for v, text in verses.items()
        if re.search(r"제\s*\d+\s*[장편]", text)
    ]
    assert leaked == [], f"장 제목이 본문에 섞였다: {leaked[:10]}"


def test_verse_size_exceptions_are_recognized_as_verse_starts(doc):
    # VERSE_SIZE_EXCEPTIONS의 세 줄(출애굽기 6:3, 이사야서 26:5, 미가서 1:2)은
    # 각각 9.96/9.96/11.22 크기로 찍혀 있어 일반 크기 필터(12.1)로는 걸리지
    # 않는다. 예외 처리가 없으면 이 절 번호는 해당 페이지의 절 시작 목록에서
    # 통째로 사라진다(9.96은 드롭, 11.22는 이어짐으로 오분류). classify_lines가
    # 이 세 절 번호를 정확히 절 시작으로 인식하는지 직접 확인한다 — 31,102라는
    # 집계 수치만으로는 이 세 줄이 깨지면 진단이 되지 않는다.
    assert 3 in [l.verse_no for l in classify_lines(doc[96]) if l.verse_no is not None]
    assert 5 in [l.verse_no for l in classify_lines(doc[881]) if l.verse_no is not None]
    assert 2 in [l.verse_no for l in classify_lines(doc[1135]) if l.verse_no is not None]


def test_pins_malachi_4_6_and_revelation_22_21():
    # 말라기 4장 6절(구약 마지막 절)과 요한계시록 22장 21절(신약 마지막 절)은
    # 각각 성경 본문이 끝나는 두 지점(권 이음매, 문서 끝)이다. 부록·해설이
    # 섞여 들어가면 정확히 이 두 절이 늘어나므로 정확한 문자열로 고정해
    # 회귀를 잡는다.
    bible = build_bible()
    assert bible["말라기"]["4"]["6"] == (
        "그가 아버지들의 마음을 자식들 에게 돌아오게 하고 자식들의 마음을 "
        "그들의 아버지들에게 돌아오게 하여 내가 와서 저주로 그 땅을 치지 "
        "아니하 게 하리라."
    )
    assert bible["요한계시록"]["22"]["21"] == (
        "우리 주 예수 그리스도의 은혜가 너희 모두와 함께 있기를 원하노라. 아멘."
    )
