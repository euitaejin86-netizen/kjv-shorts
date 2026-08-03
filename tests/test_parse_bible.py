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


import hashlib
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
    # 66권 전체 31,102절을 훑어 "제 N 장"/"제 N 편" 잔재를 잡는다.
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
        "그가 아버지들의 마음을 자식들에게 돌아오게 하고 자식들의 마음을 "
        "그들의 아버지들에게 돌아오게 하여 내가 와서 저주로 그 땅을 치지 "
        "아니하게 하리라."
    )
    assert bible["요한계시록"]["22"]["21"] == (
        "우리 주 예수 그리스도의 은혜가 너희 모두와 함께 있기를 원하노라. 아멘."
    )


# 전체 코퍼스 체크섬. 절 4개(위 두 테스트)만으로는 31,102절 중 나머지가
# 자릿수 필터·gap 대역·병합 로직이 바뀌어도 조용히 망가지는 것을 잡지 못한다
# (40%로 잘린 절, 인접 절 맞바꿈, 이어지는 줄이 옆 절로 넘어감, 같은 길이의
# 본문 치환 — 이 네 가지 뮤테이션 모두 오늘의 _validate를 통과한다).
#
# 연결 순서: BOOKS_KO 권 순서 -> 각 권 안에서 장 번호 오름차순(정수 비교) ->
# 각 장 안에서 절 번호 오름차순(정수 비교). 구분자 없이 절 본문 문자열을
# 그대로 이어 붙인다. 이 순서를 벗어나면 체크섬이 다른 값이 나오므로,
# 순서 자체가 체크섬의 일부다.
#
# 이 값이 바뀌면(의도된 변경이라면): 바뀐 절 몇 개를 실제로 눈으로 확인해
# 정상적인 변경인지 확인한 뒤, 아래 두 상수를 새로 계산해 의도적으로 갱신한다.
# "테스트가 실패하니 그냥 새 값으로 바꾼다"는 이 테스트의 존재 목적을 없앤다.
EXPECTED_TOTAL_CHARS = 2_109_446
EXPECTED_SHA256 = "303a32c18ddf5036e880e87e478e082483b0aff4ead12bf7efb2081b7c1baf74"


def test_whole_corpus_checksum():
    bible = build_bible()
    parts = []
    for book in BOOKS_KO:
        chapters = bible[book]
        for ch in sorted(chapters, key=int):
            verses = chapters[ch]
            for v in sorted(verses, key=int):
                parts.append(verses[v])
    concat = "".join(parts)
    assert len(concat) == EXPECTED_TOTAL_CHARS
    assert hashlib.sha256(concat.encode("utf-8")).hexdigest() == EXPECTED_SHA256


def test_no_spurious_space_before_particle():
    # PDF는 줄 끝 trailing space로 단어 경계를 인코딩한다("...땅을 " 다음
    # 줄 "창조하시니라."). classify_lines가 strip()으로 이를 지우고
    # build_bible이 모든 줄 경계에 " ".join으로 공백을 강제하면, 단어
    # 중간에서 줄이 끊긴 자리마다 조사 앞에 있어선 안 될 공백이 낀다
    # (예: "멸망 하지", "게난 을", "자식들 에게"). 31,102절 전체를 훑어
    # "한글 뒤 공백 뒤 조사"가 하나도 없는지 확인한다.
    #
    # 조사 후보 중 을/를/는/에/에게/으로/과 일곱 개만 검사한다. 나머지
    # (이·은·의·도·와·가·에서·만)는 실제로 돌려서 전수 확인한 결과 전부
    # 조사가 아니라 독립된 한글 단어와 겹쳐 오탐이었다:
    #   이 — 지시대명사 "이"("이 일", "이 땅" = this matter/land), 1854건
    #     전부 뒤에 명사·관형어가 옴(동사가 온 적 없음 — 조사라면 서술어가
    #     와야 하므로 오분류가 아님이 확인됨)
    #   은 — 명사 "은"(silver, "은 천 개" = a thousand pieces of silver), 71건
    #   의 — 명사 "의"(righteousness, "주의 의" = the LORD's righteousness), 23건
    #   도 — 명사 "도"(degree, "십 도" = ten degrees, 2 Kings 20 해시계), 8건
    #   와 — 동사 "오다"의 활용형("와 있는데" = having come), 4건
    #   가 — 동사 "가다"의 활용형("물러나 가" = withdrew and went), 1건
    #   에서 — 고유명사 "에서"(Esau의 한글 표기, "에서 자손" = sons of Esau), 7건
    #   만 — 숫자 단위 "만"(10,000) 또는 "가득 찬"(full, "만 일 년" = a full
    #     year), 83건
    # 위 여덟 조사는 이 성경 본문에서 독립 단어로도 매우 흔히 쓰여, 문자
    # 패턴만으로는 조사 결합과 구분할 수 없다. 을/를/는/에/에게/으로/과는
    # 이 본문에 그런 독립 단어 용례가 전혀 없어(0건 확인) 오탐 없이 그대로
    # 0을 기대할 수 있다.
    bible = build_bible()
    bad = re.compile(r"[가-힣] (을|를|는|에|에게|으로|과)\b")
    hits = [
        f"{book} {ch}:{v}: {text!r}"
        for book, chapters in bible.items()
        for ch, verses in chapters.items()
        for v, text in verses.items()
        if bad.search(text)
    ]
    assert hits == [], f"조사 앞에 스퓨리어스 공백이 남아 있다: {hits[:10]}"
