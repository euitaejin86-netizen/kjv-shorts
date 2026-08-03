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
