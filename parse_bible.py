r"""킹제임스 흠정역 PDF를 권-장-절 구조의 JSON으로 변환한다.

조판 구조는 글자 크기로 판별한다 (본문 영역 전수 집계 결과):
  12.1              절 시작        31,099줄 (KJV 총 절 수 31,102)
  11.2 / 11.6 / 11.8 절 이어짐     95,551줄
  12.5              장 제목        1,203줄  "제 1 장", 시편 "제 18 편"
  10.4              편집자 소제목  4,294줄
  10.3              시편 표제      164줄   KJV는 절 번호를 매기지 않음
  10.1 / 10.2       권 소개 블록   450줄
  12.2 이상         장식·부록 제목  버림

장 제목과 소제목을 버리지 않으면 앞 절 본문 끝에 조용히 붙는다. 절 수는
그대로라 검증도 통과하고, 그대로 영상이 되어 공개된다.

러닝 헤더의 장 번호는 실제 본문과 한 장씩 어긋나므로 쓰지 않는다.
장 구분은 절 번호가 1로 리셋되는 지점으로 판단한다.

GAP_LEFT/GAP_RIGHT (좌단·우단 사이 여백, x 100~200): 권 제목 줄(예: 18쪽
"기원이라 하는 모세의 첫째 책")이 크기 11.76으로 찍히는데, 이는 절 이어지는
줄과 같은 크기 대역(11.0~11.95)이라 크기만으로는 구분할 수 없다. 대신 이 줄은
좌단(x0 ≈ 36~46)에도 우단(x0 ≈ 217~226)에도 속하지 않고 그 사이 여백에
찍힌다. 18~1610쪽 전체를 이 여백(100≤x0<200) 조건으로 스캔한 결과 정확히
54건이 걸렸고 전수 확인 결과 전부 권 제목 줄이거나(52건) 무관한 장식
문구("INCHEON KOREA 2021" 저작권 표시 1건, "- 끝 -" 종결 표시 1건)였다.
실제 절 본문은 단 한 건도 이 여백에 없었다.

VERSE_NO 정규식의 (?!\.): 부록 목차(1578쪽)의 "1. 킹제임스 성경과 틴데일" 같은
번호 목록 항목은 크기 12.18로 절 시작 크기 대역(12.1±0.15)에 들어와 절
시작으로 오인된다. 그러나 실제 절 시작은 숫자 뒤에 항상 공백(과 선택적으로
¶)이 오지 "숫자+마침표"로 오지 않는다("1 오 나의 힘이신 주여", "10 ¶ 셈의
세대들은" 등). 이 부정 전방탐색은 숫자 뒤에 마침표가 오는 목록 항목을 절
시작에서 제외한다.
"""
import json
import re
from pathlib import Path
from typing import NamedTuple

import fitz

SOURCE_DIR = Path(r"C:\Users\uieta\KEEPBIBLE\킹제임스 자료모음")
BIBLE_PDF = SOURCE_DIR / "(KJV 성경 흠정역(한글)) 큰글자 성경 신구약 부록 2025 최적화.pdf"

OUT_JSON = Path(__file__).parent / "bible" / "kjv_ko.json"
EN_JSON = Path(__file__).parent / "bible" / "kjv_en.json"

# 정경 순서대로 나열한 흠정역 권 이름. kjv_en.json의 권 순서와 1:1로 대응한다.
# 러닝 헤더에서 뽑지 않는 이유: 요한이서·요한삼서는 시작 페이지 하나로 끝나는데
# 권 시작 페이지에는 러닝 헤더가 없어 문서 어디에도 두 권의 헤더가 존재하지 않는다.
BOOKS_KO = [
    "창세기", "출애굽기", "레위기", "민수기", "신명기",
    "여호수아기", "사사기", "룻기", "사무엘기상", "사무엘기하",
    "열왕기상", "열왕기하", "역대기상", "역대기하", "에스라",
    "느헤미야기", "에스더기", "욥기", "시편", "잠언",
    "전도서", "솔로몬의 아가", "이사야서", "예레미야서", "예레미야 애가",
    "에스겔서", "다니엘서", "호세아", "요엘", "아모스",
    "오바댜", "요나", "미가", "나훔", "하박국",
    "스바냐", "학개", "스가랴", "말라기",
    "마태복음", "마가복음", "누가복음", "요한복음", "사도행전",
    "로마서", "고린도전서", "고린도후서", "갈라디아서", "에베소서",
    "빌립보서", "골로새서", "데살로니가전서", "데살로니가후서", "디모데전서",
    "디모데후서", "디도서", "빌레몬서", "히브리서", "야고보서",
    "베드로전서", "베드로후서", "요한일서", "요한이서", "요한삼서",
    "유다서", "요한계시록",
]

HEADER_Y = 30.0          # 이보다 위는 페이지 번호·러닝 헤더
VERSE_SIZE = 12.1        # 절 시작 줄의 글자 크기
BODY_SIZE_MIN = 11.0     # 절 이어지는 줄의 최소 크기
SIZE_TOL = 0.15          # 크기 비교 허용 오차
COLUMN_SPLIT = 150.0     # 이보다 오른쪽은 우단. 이 값은 GAP_LEFT~GAP_RIGHT
                          # ([100, 200)) 여백 대역 안에 있다: 그 대역의 줄은
                          # classify_lines가 위에서 이미 continue로 버리므로,
                          # 실제로는 100 <= x0 < 200인 줄이 여기 도달하는 일이
                          # 없다. 즉 이 상수는 도달 불가능하며 "튜닝"해도
                          # 효과가 없다 — 값을 만지려면 먼저 GAP 필터부터
                          # 이해해야 한다.
GAP_LEFT = 100.0         # 좌단·우단 사이 여백 시작 x
GAP_RIGHT = 200.0        # 좌단·우단 사이 여백 끝 x (권 제목이 이 여백에 찍힌다)

VERSE_NO = re.compile(r"^(\d+)(?!\.)\s*¶?\s*")

# 실측으로 확인된, 크기 필터를 벗어나는 절 시작 예외 3건 (페이지 번호는 0-based
# fitz 인덱스, 즉 page.number). 크기 12.1 절 시작을 전수 집계하면 31,099줄로
# 실제 31,102절보다 3개 적은데, 그 차이가 이 세 줄이다. 크기 범위 자체를
# 넓히면 서문·각주처럼 숫자로 시작하는 무관한 문단까지 절 시작으로 오인하므로
# (실측 결과 30건 이상 오탐), 위치가 확인된 이 세 줄만 예외로 둔다.
#   96쪽 출애굽기 6:3   — 9.96 (정상은 12.1)
#   881쪽 이사야서 26:5 — 9.96
#   1135쪽 미가서 1:2   — 11.22 (정상 이어짐 크기 대역과 겹쳐 이어짐으로 오분류됨)
VERSE_SIZE_EXCEPTIONS = {
    (96, "3 내가 아브라함과 이삭과 야곱에"),
    (881, "5 ¶ 그분께서 높은 곳에 거하는"),
    (1135, "2 너희 모든 백성들아"),
}


class Line(NamedTuple):
    text: str
    verse_no: int | None


def classify_lines(page: fitz.Page) -> list[Line]:
    """페이지에서 본문 줄만 남기고 절 시작 여부를 표시한다.

    줄 끝 공백은 그대로 남긴다. PDF는 단어가 줄 끝에서 끝나면 trailing
    space를 찍고, 단어 중간에서 줄이 끊기면 공백을 찍지 않는다 — 이 공백이
    한글 조사 앞뒤 띄어쓰기의 유일한 근거다. 여기서 strip()으로 지워버리면
    build_bible이 모든 줄 경계에 공백을 넣을 수밖에 없어 "멸망 하지",
    "게난 을"처럼 단어 중간에 공백이 끼어든다. 왼쪽 공백만 지운다.
    """
    raw = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:  # 이미지 블록 제외
            continue
        for ln in block["lines"]:
            text = "".join(s["text"] for s in ln["spans"]).lstrip()
            x0 = ln["bbox"][0]
            if not text.strip() or ln["bbox"][1] < HEADER_Y:
                continue
            if GAP_LEFT <= x0 < GAP_RIGHT:
                continue  # 좌단·우단 사이 여백: 권 제목 등 장식 줄이 찍히는 자리
            size = ln["spans"][0]["size"]
            is_verse = abs(size - VERSE_SIZE) <= SIZE_TOL
            is_body = BODY_SIZE_MIN <= size < VERSE_SIZE - SIZE_TOL
            if not is_verse and any(
                text.startswith(prefix)
                for pg, prefix in VERSE_SIZE_EXCEPTIONS
                if pg == page.number
            ):
                is_verse = True
            if not (is_verse or is_body):
                continue  # 장 제목(12.5), 소제목(10.4), 표제(10.3), 소개(10.2), 장식
            raw.append((x0, ln["bbox"][1], text, is_verse))

    # 2단 조판: 좌단을 y순으로 모두 읽은 뒤 우단으로 넘어간다.
    out: list[Line] = []
    for column in (
        sorted((r for r in raw if r[0] < COLUMN_SPLIT), key=lambda r: r[1]),
        sorted((r for r in raw if r[0] >= COLUMN_SPLIT), key=lambda r: r[1]),
    ):
        for _x0, _y0, text, is_verse in column:
            m = VERSE_NO.match(text) if is_verse else None
            if m:
                # VERSE_NO가 앞의 "9 ¶ " 형태를 통째로 삼키므로 남는 줄 끝
                # 공백은 그대로 둔다. 앞쪽 잔여 공백만 방어적으로 지운다.
                out.append(Line(VERSE_NO.sub("", text).lstrip(), int(m.group(1))))
            else:
                # 이어지는 줄 중간에 낀 ¶(문단 표시)는 공백 하나로 정규화한다.
                # 그냥 지우면 "...끝¶다음..." 같은 줄에서 단어가 붙어버린다.
                # 여기서는 lstrip()을 다시 하지 않는다 — 실제 성경 이어짐 줄은
                # PDF에서 앞 공백 없이 시작하지만(수집 시점에 이미 한 번
                # lstrip했다), ¶가 줄 맨 앞에 오는 드문 경우(예: 서신 끝의
                # "¶ 로마 사람들에게...") 치환이 만든 공백을 다시 지우면 앞
                # 절과 공백 없이 붙어버린다.
                out.append(Line(re.sub(r"\s*¶\s*", " ", text), None))
    return out


def load_expected_structure() -> list[dict[int, int]]:
    """영어 KJV에서 권별 {장번호: 절수} 표를 만든다. 한글 파싱의 정답지다."""
    data = json.loads(EN_JSON.read_text(encoding="utf-8"))
    return [
        {c["chapter"]: len(c["verses"]) for c in book["chapters"]}
        for book in data["books"]
    ]


def load_expected_text() -> list[dict[int, dict[int, str]]]:
    """영어 KJV 원문 텍스트 표 {장번호: {절번호: 본문}}. 길이 비율로 본문 오염
    (예: 절 사이에 낀 해설·주석)을 검출하는 데 쓴다. 절 수 검증만으로는
    본문 안에 섞여 들어간 수천 자짜리 다른 글을 잡아낼 수 없다."""
    data = json.loads(EN_JSON.read_text(encoding="utf-8"))
    return [
        {c["chapter"]: {v["verse"]: v["text"] for v in c["verses"]} for c in book["chapters"]}
        for book in data["books"]
    ]


def build_bible() -> dict[str, dict[str, dict[str, str]]]:
    """PDF 전체를 파싱해 권-장-절 구조를 만들고 영어 KJV와 대조한다."""
    doc = fitz.open(BIBLE_PDF)
    names = BOOKS_KO
    expected = load_expected_structure()
    expected_text = load_expected_text()

    bible: dict[str, dict[str, dict[str, str]]] = {n: {} for n in names}
    bi = ci = 0                      # 현재 권 인덱스, 현재 장 인덱스(0-based)
    prev_verse = 0
    buf: list[str] = []              # 현재 절의 줄 조각
    cur: tuple[str, str, str] | None = None   # (권, 장, 절)
    book_done = False                # 현재 권의 마지막 절까지 다 받았는가

    def flush():
        if cur is not None:
            book, chap, verse = cur
            # PDF 줄 끝 공백이 이미 단어 경계를 인코딩하고 있으므로("...땅을 "
            # 다음 줄 "창조하시니라." 처럼) 여기서 공백을 새로 넣지 않는다.
            # classify_lines가 보존한 trailing space만으로 이어 붙인다.
            bible[book].setdefault(chap, {})[verse] = "".join(buf).strip()

    for page in doc:
        lines = classify_lines(page)

        # 권 경계: 한 권의 마지막 절을 다 받은 뒤 절 시작이 하나도 없는
        # 페이지는 성경 본문이 아니라 삽입된 해설·부록이다(예: 말라기와
        # 마태복음 사이의 신구약 중간기 해설, 계시록 뒤 부록·연대표·MEMO).
        # 그런 페이지는 통째로 건너뛴다. 다음 권 1절이든 뭐든 절 시작이
        # 하나라도 있는 페이지는 정상 처리하므로, 마지막 절이 다음 쪽으로
        # 정상적으로 이어지는 경우는 그대로 붙는다. 이 규칙 하나로 66권
        # 사이 모든 이음매와 계시록 뒤 부록을 함께 막는다.
        if book_done and not any(l.verse_no is not None for l in lines):
            continue

        for line in lines:
            if line.verse_no is None:
                buf.append(line.text)
                continue

            flush()
            n = line.verse_no

            if n == 1 and prev_verse != 0:
                # 절이 1로 리셋됐다. 현재 권의 장을 다 채웠으면 다음 권, 아니면 다음 장.
                if ci + 1 >= len(expected[bi]):
                    bi += 1
                    ci = 0
                    if bi >= len(names):
                        flush()
                        _validate(bible, names, expected, expected_text)
                        return bible
                else:
                    ci += 1

            if n != 1 and n != prev_verse + 1:
                # 절 번호가 이전 절의 다음 번호가 아니다: 같은 번호 재사용(중복)
                # 또는 역순이다. 이 검사가 없으면 스퓨리어스 절 시작이 같은 장
                # 안의 기존 절 번호를 그대로 덮어써도(dict 대입) 길이 검증과
                # range(1, want_n+1) 키 검증을 모두 통과한다 — 부록 목차 버그와
                # 같은 부류의 무결성 구멍이다.
                raise ValueError(
                    f"{names[bi]} {ci+1}장: 절 번호 {prev_verse} -> {n} (중복·역순)"
                )

            cur = (names[bi], str(ci + 1), str(n))
            buf = [line.text]
            prev_verse = n
            last_chap = max(expected[bi])
            book_done = ci + 1 == last_chap and n == expected[bi][last_chap]

    flush()
    _validate(bible, names, expected, expected_text)
    return bible


MAX_LEN_RATIO = 3.0  # 한글 절 길이 / 영어 절 길이. 실측 분포: 중앙값 0.525,
# p99 0.815, 정상 범위 안 최악의 예외가 1.56. 오염된 말라기 4:6은 26.28이었다.
# 3.0은 양쪽 모두에 넉넉한 여유를 둔 값이라 오탐도, 이런 오염을 놓칠 일도 없다.


def _validate(bible, names, expected, expected_text):
    """영어 KJV 구조와 한 절도 어긋나지 않는지 확인한다.

    잘못 파싱된 구절은 조용히 통과하면 그대로 영상이 되어 공개된다.
    이 검증은 생략할 수 없다.
    """
    for i, name in enumerate(names):
        got, want = bible[name], expected[i]
        en_text = expected_text[i]
        if len(got) != len(want):
            raise ValueError(f"{name}: 장 수 {len(got)}, 기대 {len(want)}")
        for chap, want_n in want.items():
            verses = got.get(str(chap))
            if verses is None:
                raise ValueError(f"{name} {chap}장이 없다")
            if len(verses) != want_n:
                raise ValueError(f"{name} {chap}장: 절 수 {len(verses)}, 기대 {want_n}")
            for v in range(1, want_n + 1):
                text = verses.get(str(v))
                if not text or not text.strip():
                    raise ValueError(f"{name} {chap}:{v} 본문이 비어 있다")
                en = en_text[chap][v]
                ratio = len(text) / len(en) if en else 0
                if ratio > MAX_LEN_RATIO:
                    raise ValueError(
                        f"{name} {chap}:{v} 길이 비율 {ratio:.2f}"
                        f"(본문 {len(text)}자 / 영어 {len(en)}자)가 임계값 "
                        f"{MAX_LEN_RATIO}를 넘었다 — 본문 오염 의심"
                    )


def main():
    bible = build_bible()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(bible, ensure_ascii=False), encoding="utf-8")
    total = sum(len(v) for ch in bible.values() for v in ch.values())
    print(f"wrote {OUT_JSON} ({len(bible)} books, {total} verses)")


if __name__ == "__main__":
    main()
