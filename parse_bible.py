"""킹제임스 흠정역 PDF를 권-장-절 구조의 JSON으로 변환한다.

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

VERSE_NO = re.compile(r"^(\d+)\s*¶?\s*")


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
