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
import re
from pathlib import Path
from typing import NamedTuple

import fitz

SOURCE_DIR = Path(r"C:\Users\uieta\KEEPBIBLE\킹제임스 자료모음")
BIBLE_PDF = SOURCE_DIR / "(KJV 성경 흠정역(한글)) 큰글자 성경 신구약 부록 2025 최적화.pdf"

HEADER_Y = 30.0          # 이보다 위는 페이지 번호·러닝 헤더
VERSE_SIZE = 12.1        # 절 시작 줄의 글자 크기
BODY_SIZE_MIN = 11.0     # 절 이어지는 줄의 최소 크기
SIZE_TOL = 0.15          # 크기 비교 허용 오차
COLUMN_SPLIT = 150.0     # 이보다 오른쪽은 우단
GAP_LEFT = 100.0         # 좌단·우단 사이 여백 시작 x
GAP_RIGHT = 200.0        # 좌단·우단 사이 여백 끝 x (권 제목이 이 여백에 찍힌다)

VERSE_NO = re.compile(r"^(\d+)(?!\.)\s*¶?\s*")


class Line(NamedTuple):
    text: str
    verse_no: int | None


def classify_lines(page: fitz.Page) -> list[Line]:
    """페이지에서 본문 줄만 남기고 절 시작 여부를 표시한다."""
    raw = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:  # 이미지 블록 제외
            continue
        for ln in block["lines"]:
            text = "".join(s["text"] for s in ln["spans"]).strip()
            x0 = ln["bbox"][0]
            if not text or ln["bbox"][1] < HEADER_Y:
                continue
            if GAP_LEFT <= x0 < GAP_RIGHT:
                continue  # 좌단·우단 사이 여백: 권 제목 등 장식 줄이 찍히는 자리
            size = ln["spans"][0]["size"]
            is_verse = abs(size - VERSE_SIZE) <= SIZE_TOL
            is_body = BODY_SIZE_MIN <= size < VERSE_SIZE - SIZE_TOL
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
                out.append(Line(VERSE_NO.sub("", text).strip(), int(m.group(1))))
            else:
                out.append(Line(text.replace("¶", "").strip(), None))
    return out
