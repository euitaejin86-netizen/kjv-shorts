# 킹제임스 묵상 쇼츠 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 킹제임스 흠정역 PDF에서 성경 본문을 구조화해 뽑고, 대본 JSON 하나로 9:16 묵상 쇼츠 MP4를 자동 생성하며, 사람이 확인한 뒤 유튜브에 예약 업로드하는 파이프라인을 만든다.

**Architecture:** 서로 import하지 않는 독립 스크립트 4개가 파일을 통해서만 소통한다. `parse_bible.py`와 `extract_corpus.py`는 최초 1회만 실행해 `bible/kjv_ko.json`과 `corpus/*.txt`를 만든다. 이후 매주 Claude Code가 대본 JSON을 쓰고, `build.py`가 그것 하나만 받아 MP4까지 렌더링하며, 사람이 영상을 확인한 뒤 `upload.py`를 직접 실행한다.

**Tech Stack:** Python 3.14, PyMuPDF (PDF 추출), edge-tts (음성), FFmpeg (렌더링), google-api-python-client (업로드), pytest (테스트)

## Global Constraints

- 프로젝트 루트: `C:\Users\uieta\KEEPBIBLE\kjv-shorts`
- 소스 PDF 폴더: `C:\Users\uieta\KEEPBIBLE\킹제임스 자료모음` — **읽기 전용. 어떤 파일도 쓰거나 수정하지 않는다.**
- 본문 PDF 파일명: `(KJV 성경 흠정역(한글)) 큰글자 성경 신구약 부록 2025 최적화.pdf`
- 영상 규격: 1080×1920 (9:16), 30fps, H.264 (`libx264`), `yuv420p`, 오디오 AAC
- TTS 음성: 한국어 `ko-KR-InJoonNeural`, 영어 `en-GB-RyanNeural`
- 파일 인코딩: 모든 JSON·텍스트 파일 입출력은 **반드시 `encoding="utf-8"` 명시**. Windows 기본 인코딩(cp949)으로 열면 한글이 깨진다.
- 경로에 한글·공백·괄호가 포함되므로 셸 명령에서 항상 따옴표로 감싼다.
- `bible/`, `corpus/`, `out/`은 `.gitignore`에 등재되어 있다. 생성물을 커밋하지 않는다.
- 저작권: 영어 KJV는 퍼블릭 도메인. 한글 흠정역은 '그리스도예수안에' 출판사 저작물이며 생성물을 저장소에 커밋하지 않는 이유이기도 하다.

---

## File Structure

| 파일 | 책임 | 실행 빈도 |
|---|---|---|
| `parse_bible.py` | 본문 PDF → `bible/kjv_ko.json` (검증 포함) | 1회 |
| `fetch_kjv_en.py` | 영어 KJV 다운로드 → `bible/kjv_en.json` | 1회 |
| `extract_corpus.py` | 주석 PDF 109개 → `corpus/*.txt` | 1회 |
| `build.py` | 대본 JSON → `out/*.mp4` | 매번 |
| `upload.py` | MP4 → 유튜브 예약 업로드 | 매번 |
| `topics.json` | 주제 로테이션 상태 | 수동 편집 |
| `tests/test_parse_bible.py` | 파서 단위 테스트 | CI 없음, 수동 |

`parse_bible.py`는 순수 함수(페이지 → 분류된 줄, 줄 → 구조)와 I/O를 분리해 테스트 가능하게 둔다. 나머지는 절차적 스크립트로 충분하다.

---

### Task 1: 환경 준비와 영어 KJV 확보

**Files:**
- Create: `fetch_kjv_en.py`
- Create: `requirements.txt`

**Interfaces:**
- Consumes: 없음
- Produces: `bible/kjv_en.json` — 구조는
  `{"translation": str, "books": [{"name": str, "chapters": [{"chapter": int, "verses": [{"verse": int, "text": str}]}]}]}`.
  이후 모든 태스크가 이 구조를 신뢰한다.

- [ ] **Step 1: FFmpeg 설치**

FFmpeg이 설치되어 있지 않다. winget으로 설치한다.

```bash
winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
```

설치 후 **새 셸을 열어야** PATH가 반영된다.

- [ ] **Step 2: FFmpeg 설치 확인**

Run: `ffmpeg -version` 그리고 `ffprobe -version`
Expected: 두 명령 모두 버전 문자열 출력. `command not found`가 나오면 PATH 반영을 위해 셸을 다시 열 것.

- [ ] **Step 3: 파이썬 의존성 파일 작성**

`requirements.txt`:

```
pymupdf>=1.28
edge-tts>=7.2
google-api-python-client>=2.100
google-auth-oauthlib>=1.2
pytest>=8.0
```

- [ ] **Step 4: 의존성 설치**

```bash
python -m pip install -r requirements.txt
```

Run: `python -c "import fitz, edge_tts, pytest; print('ok')"`
Expected: `ok`

- [ ] **Step 5: 영어 KJV 다운로드 스크립트 작성**

`fetch_kjv_en.py`:

```python
"""영어 KJV(퍼블릭 도메인)를 내려받아 bible/kjv_en.json으로 저장한다.

이 파일은 영상에 넣을 영어 구절의 출처이자, parse_bible.py가 한글 파싱 결과를
대조하는 구조 검증기 역할을 한다.
"""
import json
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/KJV.json"
OUT = Path(__file__).parent / "bible" / "kjv_en.json"

# KJV의 널리 알려진 정경 수치. 다운로드한 파일이 다른 번역본으로 바뀌었는지 잡는다.
EXPECTED_BOOKS = 66
EXPECTED_VERSES = 31102


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {URL}")
    with urllib.request.urlopen(URL) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    books = data["books"]
    total = sum(len(c["verses"]) for b in books for c in b["chapters"])

    assert len(books) == EXPECTED_BOOKS, f"books={len(books)}, expected {EXPECTED_BOOKS}"
    assert total == EXPECTED_VERSES, f"verses={total}, expected {EXPECTED_VERSES}"

    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} ({len(books)} books, {total} verses)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 실행해서 검증 통과 확인**

Run: `python fetch_kjv_en.py`
Expected: `wrote ...\bible\kjv_en.json (66 books, 31102 verses)`

assert가 걸리면 다운로드 URL이 다른 내용으로 바뀐 것이므로 진행하지 말고 원인을 확인한다.

- [ ] **Step 7: 커밋**

```bash
git add requirements.txt fetch_kjv_en.py
git commit -m "feat: add English KJV fetcher with canon verification"
```

---

### Task 2: 페이지에서 본문 줄 분류하기

PDF 페이지 하나를 받아 "절 시작 줄"과 "이어지는 줄"만 남기고 페이지 번호·러닝 헤더·소제목·권 소개 블록을 걷어내는 순수 함수를 만든다. 다음 태스크가 이 결과를 구조로 조립한다.

**Files:**
- Create: `parse_bible.py`
- Create: `tests/test_parse_bible.py`

**Interfaces:**
- Consumes: 없음 (PyMuPDF의 `page.get_text("dict")`만 사용)
- Produces:
  - `classify_lines(page) -> list[Line]` — `Line`은 `NamedTuple("Line", text=str, verse_no=int|None)`.
    `verse_no`가 정수면 그 절이 시작하는 줄, `None`이면 앞 절에서 이어지는 줄.
  - `BIBLE_PDF: Path` 상수

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_parse_bible.py`:

```python
import fitz
import pytest

from parse_bible import BIBLE_PDF, classify_lines


@pytest.fixture(scope="module")
def doc():
    return fitz.open(BIBLE_PDF)


def test_drops_page_number_and_running_header(doc):
    # 페이지 30은 상단에 "13"(페이지 번호)과 "창세기 12"(러닝 헤더)를 갖는다.
    lines = classify_lines(doc[30])
    texts = [l.text for l in lines]
    assert "13" not in texts
    assert "창세기 12" not in texts


def test_marks_verse_starts(doc):
    # 페이지 30 좌단은 창세기 11:8로 시작한다.
    lines = classify_lines(doc[30])
    starts = [l.verse_no for l in lines if l.verse_no is not None]
    assert starts[:4] == [8, 9, 10, 11]


def test_continuation_lines_have_no_verse_no(doc):
    lines = classify_lines(doc[30])
    # 첫 줄은 앞 페이지에서 넘어온 이어지는 줄이다.
    assert lines[0].verse_no is None


def test_drops_editor_section_headings(doc):
    # 페이지 1550(요한의 둘째 서신)에는 "진리 안에서 걸으라" 소제목이 있다.
    texts = [l.text for l in classify_lines(doc[1550])]
    assert not any("진리 안에서 걸으라" == t for t in texts)


def test_drops_book_intro_block(doc):
    # 권 시작 페이지의 소개 블록("기록자:", "핵심 절:" 등)이 남으면 안 된다.
    texts = " ".join(l.text for l in classify_lines(doc[1550]))
    assert "기록자:" not in texts
    assert "핵심 절:" not in texts


def test_two_column_reading_order(doc):
    # 좌단을 모두 읽은 뒤 우단으로 넘어가야 절 번호가 단조 증가한다.
    starts = [l.verse_no for l in classify_lines(doc[1550]) if l.verse_no is not None]
    assert starts == sorted(starts)
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인**

Run: `python -m pytest tests/test_parse_bible.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'parse_bible'`

- [ ] **Step 3: 최소 구현 작성**

`parse_bible.py`:

```python
"""킹제임스 흠정역 PDF를 권-장-절 구조의 JSON으로 변환한다.

조판 구조 (실측):
  절 시작 줄   크기 12.1, 좌단 x=46 / 우단 x=226  (본문보다 9pt 들여쓰기)
  이어지는 줄  크기 11.8 내외, 좌단 x=37 / 우단 x=217
  소제목       크기 10.4, 가운데 정렬
  페이지 헤더  크기 10.9, y≈19
  권 소개      크기 10.2~10.4, 권 시작 페이지에만

러닝 헤더의 장 번호는 실제 본문과 한 장씩 어긋나므로 신뢰하지 않는다.
장 구분은 절 번호가 1로 리셋되는 지점으로 판단한다.
"""
import re
from pathlib import Path
from typing import NamedTuple

import fitz

SOURCE_DIR = Path(r"C:\Users\uieta\KEEPBIBLE\킹제임스 자료모음")
BIBLE_PDF = SOURCE_DIR / "(KJV 성경 흠정역(한글)) 큰글자 성경 신구약 부록 2025 최적화.pdf"

HEADER_Y = 30.0        # 이보다 위는 페이지 번호·러닝 헤더
BODY_SIZE_MIN = 11.0   # 이보다 작은 글씨는 소제목이거나 권 소개 블록
COLUMN_SPLIT = 150.0   # 이보다 오른쪽은 우단
INDENT = 4.0           # 단 왼쪽 끝에서 이만큼 이상 들여썼으면 절 시작

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
            if not text:
                continue
            x0, y0 = ln["bbox"][0], ln["bbox"][1]
            size = ln["spans"][0]["size"]
            if y0 < HEADER_Y:          # 페이지 번호·러닝 헤더
                continue
            if size < BODY_SIZE_MIN:   # 소제목·권 소개 블록
                continue
            raw.append((x0, y0, text))

    if not raw:
        return []

    # 2단 조판: 좌단을 y순으로 모두 읽은 뒤 우단으로 넘어간다.
    left = sorted((r for r in raw if r[0] < COLUMN_SPLIT), key=lambda r: r[1])
    right = sorted((r for r in raw if r[0] >= COLUMN_SPLIT), key=lambda r: r[1])

    out: list[Line] = []
    for column in (left, right):
        if not column:
            continue
        margin = min(r[0] for r in column)  # 그 단의 왼쪽 끝
        for x0, _y0, text in column:
            m = VERSE_NO.match(text)
            if m and x0 - margin >= INDENT:
                out.append(Line(VERSE_NO.sub("", text), int(m.group(1))))
            else:
                out.append(Line(text.replace("¶", "").strip(), None))
    return out
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인**

Run: `python -m pytest tests/test_parse_bible.py -v`
Expected: 6개 테스트 모두 PASS

실패하면 실제 좌표를 눈으로 확인해 상수(`HEADER_Y`, `BODY_SIZE_MIN`, `COLUMN_SPLIT`, `INDENT`)를 조정한다. 확인용 명령:

```bash
python -c "import fitz; from parse_bible import BIBLE_PDF; d=fitz.open(BIBLE_PDF); [print(f\"{l['bbox'][0]:.0f} {l['bbox'][1]:.0f} {l['spans'][0]['size']:.1f} {''.join(s['text'] for s in l['spans'])[:40]}\") for b in d[30].get_text('dict')['blocks'] if b.get('type')==0 for l in b['lines']]"
```

- [ ] **Step 5: 커밋**

```bash
git add parse_bible.py tests/test_parse_bible.py
git commit -m "feat: classify Bible PDF lines into verse starts and continuations"
```

---

### Task 3: 줄을 권-장-절 구조로 조립하고 검증

Task 2의 줄 목록을 문서 전체에 걸쳐 이어 붙여 `bible/kjv_ko.json`을 만든다. 영어 KJV 구조와 대조해 한 절이라도 어긋나면 파일을 쓰지 않고 중단한다.

**Files:**
- Modify: `parse_bible.py` (Task 2에서 만든 파일에 추가)
- Modify: `tests/test_parse_bible.py` (테스트 추가)

**Interfaces:**
- Consumes: `classify_lines(page) -> list[Line]`, `BIBLE_PDF` (Task 2), `bible/kjv_en.json` (Task 1)
- Produces: `bible/kjv_ko.json` — 구조는
  `{"권이름": {"장번호(str)": {"절번호(str)": "본문"}}}`.
  권 이름은 러닝 헤더에서 얻은 한글 짧은 이름(예: `"히브리서"`).
  `build.py`가 이 구조를 그대로 읽는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_parse_bible.py` 끝에 추가:

```python
import json
from pathlib import Path

from parse_bible import book_short_names, build_bible, load_expected_structure


def test_book_short_names_finds_all_66():
    names = book_short_names(fitz.open(BIBLE_PDF))
    assert len(names) == 66
    assert names[0] == "창세기"
    assert names[-1] == "요한계시록"
    # 단일 장 책은 러닝 헤더에 장 번호가 없다. 누락되기 쉬운 지점이다.
    for n in ("오바댜", "빌레몬서"):
        assert n in names


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
    assert bible["창세기"]["1"]["1"].startswith("처음에")
    assert "믿음은" in bible["히브리서"]["11"]["1"]
    # 어느 절도 비어 있지 않다
    assert all(v.strip() for ch in bible.values() for vs in ch.values() for v in vs.values())
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인**

Run: `python -m pytest tests/test_parse_bible.py -v`
Expected: FAIL — `ImportError: cannot import name 'book_short_names' from 'parse_bible'`

- [ ] **Step 3: 구현 추가**

`parse_bible.py`에 추가:

```python
import json

OUT_JSON = Path(__file__).parent / "bible" / "kjv_ko.json"
EN_JSON = Path(__file__).parent / "bible" / "kjv_en.json"

# 러닝 헤더는 "창세기 12"처럼 장 번호가 붙거나, 단일 장 책은 "오바댜"처럼 이름만 온다.
HEADER_LINE = re.compile(r"^(\D+?)\s*\d*$")


def book_short_names(doc: fitz.Document) -> list[str]:
    """러닝 헤더에서 권의 한글 짧은 이름을 등장 순서대로 뽑는다.

    러닝 헤더는 장 번호가 한 장씩 어긋나 있어 장 판단에는 못 쓰지만,
    권 이름을 얻는 용도로는 신뢰할 수 있다.
    """
    names: list[str] = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for ln in block["lines"]:
                if ln["bbox"][1] >= HEADER_Y:
                    continue
                text = "".join(s["text"] for s in ln["spans"]).strip()
                m = HEADER_LINE.match(text)
                if not m:
                    continue
                name = m.group(1).strip()
                if not name or name in names:
                    continue
                names.append(name)
        if len(names) == 66:
            break
    return names


def load_expected_structure() -> list[dict[int, int]]:
    """영어 KJV에서 권별 {장번호: 절수} 표를 만든다. 한글 파싱의 정답지다."""
    data = json.loads(EN_JSON.read_text(encoding="utf-8"))
    return [
        {c["chapter"]: len(c["verses"]) for c in book["chapters"]}
        for book in data["books"]
    ]


def build_bible() -> dict[str, dict[str, dict[str, str]]]:
    """PDF 전체를 파싱해 권-장-절 구조를 만들고 영어 KJV와 대조한다."""
    doc = fitz.open(BIBLE_PDF)
    names = book_short_names(doc)
    expected = load_expected_structure()
    if len(names) != 66:
        raise ValueError(f"권 이름을 {len(names)}개만 찾았다. 66개여야 한다: {names}")

    bible: dict[str, dict[str, dict[str, str]]] = {n: {} for n in names}
    bi = ci = 0                      # 현재 권 인덱스, 현재 장 인덱스(0-based)
    prev_verse = 0
    buf: list[str] = []              # 현재 절의 줄 조각
    cur: tuple[str, str, str] | None = None   # (권, 장, 절)

    def flush():
        if cur is not None:
            book, chap, verse = cur
            bible[book].setdefault(chap, {})[verse] = " ".join(buf).strip()

    for page in doc:
        for line in classify_lines(page):
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
                    if bi >= 66:
                        flush()
                        _validate(bible, names, expected)
                        return bible
                else:
                    ci += 1

            cur = (names[bi], str(ci + 1), str(n))
            buf = [line.text]
            prev_verse = n

    flush()
    _validate(bible, names, expected)
    return bible


def _validate(bible, names, expected):
    """영어 KJV 구조와 한 절도 어긋나지 않는지 확인한다.

    잘못 파싱된 구절은 조용히 통과하면 그대로 영상이 되어 공개된다.
    이 검증은 생략할 수 없다.
    """
    for i, name in enumerate(names):
        got, want = bible[name], expected[i]
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


def main():
    bible = build_bible()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(bible, ensure_ascii=False), encoding="utf-8")
    total = sum(len(v) for ch in bible.values() for v in ch.values())
    print(f"wrote {OUT_JSON} ({len(bible)} books, {total} verses)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인**

Run: `python -m pytest tests/test_parse_bible.py -v`
Expected: 9개 테스트 모두 PASS

실패는 대부분 다음 셋 중 하나다. 검증이 어긋난 첫 지점을 알려주므로 그 권·장을 직접 열어 확인한다.

1. 권 이름을 66개 못 찾음 → `HEADER_LINE` 정규식이나 `HEADER_Y` 조정
2. 특정 권의 절 수 불일치 → 그 권 시작 페이지에서 소제목·소개 블록이 본문으로 새어 들어왔는지 확인
3. 장 경계 오판 → 절 번호 리셋 로직 확인. 시편처럼 장이 많은 권에서 드러나기 쉽다.

- [ ] **Step 5: 실제로 실행해 JSON 생성**

Run: `python parse_bible.py`
Expected: `wrote ...\bible\kjv_ko.json (66 books, 31102 verses)`

- [ ] **Step 6: 눈으로 최종 확인**

Run:

```bash
python -c "import json; b=json.load(open('bible/kjv_ko.json',encoding='utf-8')); print(b['창세기']['1']['1']); print(b['요한복음']['3']['16']); print(b['요한계시록']['22']['21'])"
```

Expected: 세 구절이 온전한 한글 문장으로 출력된다. 숫자나 소제목이 섞여 있으면 안 된다.

- [ ] **Step 7: 커밋**

```bash
git add parse_bible.py tests/test_parse_bible.py
git commit -m "feat: assemble Bible structure and validate against English KJV"
```

---

### Task 4: 주석 자료 텍스트 추출

주석·강해 PDF 109개를 텍스트로 뽑아 `corpus/`에 넣는다. Claude Code가 대본을 쓸 때 `grep`으로 교리적 근거를 찾는 용도다.

**Files:**
- Create: `extract_corpus.py`

**Interfaces:**
- Consumes: `SOURCE_DIR`, `BIBLE_PDF` (Task 2의 `parse_bible.py`에서 import)
- Produces: `corpus/<원본파일명>.txt` — 평문 UTF-8. 다른 스크립트가 읽지 않고 사람과 Claude Code가 `grep`으로만 쓴다.

- [ ] **Step 1: 스크립트 작성**

`extract_corpus.py`:

```python
"""주석·강해 PDF를 텍스트로 추출해 corpus/에 넣는다.

대본을 쓸 때 grep으로 주제별 근거 자료를 찾기 위한 것이다.
별도의 주제 태깅 시스템을 두지 않는 이유는 grep이 그 역할을 하기 때문이다.
"""
from pathlib import Path

import fitz

from parse_bible import BIBLE_PDF, SOURCE_DIR

OUT_DIR = Path(__file__).parent / "corpus"

# 성경 본문 PDF는 제외한다. 코퍼스에 섞이면 grep 결과가 성경 구절로 뒤덮인다.
SKIP = {BIBLE_PDF.name, "큰글자-신구약2011_iPad.pdf"}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = [p for p in SOURCE_DIR.iterdir()
            if p.suffix.lower() == ".pdf" and p.name not in SKIP]
    print(f"{len(pdfs)} PDFs to extract")

    for i, pdf in enumerate(sorted(pdfs), 1):
        out = OUT_DIR / (pdf.stem + ".txt")
        if out.exists():
            continue  # 중단 후 재실행할 수 있게 이미 뽑은 것은 건너뛴다
        try:
            with fitz.open(pdf) as doc:
                text = "\n".join(page.get_text() for page in doc)
            out.write_text(text, encoding="utf-8")
            print(f"[{i}/{len(pdfs)}] {pdf.name} -> {len(text):,} chars")
        except Exception as e:
            # 한 파일이 깨져도 나머지 108개는 계속 뽑는다
            print(f"[{i}/{len(pdfs)}] FAILED {pdf.name}: {e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행**

Run: `python extract_corpus.py`
Expected: 109개 파일에 대해 진행 상황이 출력된다. 몇 분 걸린다. 일부 FAILED가 나와도 전체가 멈추지 않아야 한다.

- [ ] **Step 3: 결과 확인**

Run:

```bash
python -c "from pathlib import Path; f=list(Path('corpus').glob('*.txt')); print(len(f),'files'); print(sum(p.stat().st_size for p in f)//1024//1024,'MB')"
```

Expected: 100개 이상, 수십 MB. 0개면 `SOURCE_DIR` 경로를 확인한다.

- [ ] **Step 4: grep이 실제로 쓸 만한지 확인**

Run: `grep -rl "믿음" corpus/ | head -5`
Expected: 파일 경로 몇 개가 나온다. 아무것도 안 나오면 인코딩 문제이므로 텍스트 파일을 직접 열어 확인한다.

- [ ] **Step 5: 커밋**

```bash
git add extract_corpus.py
git commit -m "feat: extract commentary PDFs to greppable text corpus"
```

---

### Task 5: 대본 JSON에서 MP4 렌더링

이 프로젝트의 산출물을 만드는 태스크다. 대본 JSON 하나를 받아 TTS로 음성을 만들고, 자막을 입히고, Ken Burns 배경 위에 얹어 9:16 MP4를 뽑는다.

**Files:**
- Create: `build.py`
- Create: `topics.json`
- Create: `bg/README.md`
- Create: `scripts/example.json`

**Interfaces:**
- Consumes: `bible/kjv_ko.json`, `bible/kjv_en.json` (사람과 Claude Code가 대본을 쓸 때 참조), `bg/*.jpg`
- Produces: `out/<대본파일명>.mp4` — 1080×1920 H.264/AAC. `upload.py`가 이 파일을 받는다.
- 대본 JSON 스키마 (Claude Code와 코드 사이의 계약):
  `{"topic": str, "ref": str, "verse_ko": str, "verse_en": str, "narration": list[str], "bg": str}`

- [ ] **Step 1: 배경 이미지 준비 안내 작성**

`bg/README.md`:

```markdown
# 배경 이미지

1080×1920 이상의 세로 이미지를 여기에 넣는다. 무료 출처: Unsplash, Pexels.

대본 JSON의 `bg` 필드가 이 폴더의 파일을 가리킨다 (예: `"bg": "bg/dawn.jpg"`).

매 실행마다 새로 내려받지 않는다. 몇 장 받아두고 주제별로 골라 쓴다.
```

`bg/`에 세로 이미지를 최소 1장 넣는다. 없으면 아래 명령으로 임시 단색 배경을 만들어 진행할 수 있다.

```bash
ffmpeg -f lavfi -i color=c=0x1a2634:s=1080x1920 -frames:v 1 bg/plain.jpg
```

- [ ] **Step 2: 주제 로테이션 파일 작성**

`topics.json`:

```json
{
  "next": 0,
  "topics": ["믿음", "구원", "은혜", "회개", "기도", "소망", "사랑"]
}
```

- [ ] **Step 3: 예시 대본 작성**

`scripts/example.json` — 구절 본문은 `bible/kjv_ko.json`과 `bible/kjv_en.json`에서 그대로 옮긴 값이어야 한다. 기억에 의존해 쓰지 않는다.

```json
{
  "topic": "믿음",
  "ref": "히브리서 11:1",
  "verse_ko": "이제 믿음은 바라는 것들의 실체요, 보이지 않는 것들의 증거니",
  "verse_en": "Now faith is the substance of things hoped for, the evidence of things not seen.",
  "narration": [
    "믿음은 감정이 아닙니다.",
    "아직 보이지 않는 것을 붙드는 실체입니다.",
    "오늘 당신이 붙들고 있는 것은 무엇입니까?"
  ],
  "bg": "bg/plain.jpg"
}
```

- [ ] **Step 4: 렌더링 스크립트 작성**

`build.py`:

```python
"""대본 JSON 하나를 받아 9:16 묵상 쇼츠 MP4를 만든다.

영상 구성 순서는 고정이다:
  1. 구절 카드 (무음, VERSE_CARD_SEC 초)
  2. 영어 구절 낭독
  3. 한글 구절 낭독
  4. 묵상 해설 (문장 단위)
"""
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "out"

VOICE_KO = "ko-KR-InJoonNeural"
VOICE_EN = "en-GB-RyanNeural"

W, H, FPS = 1080, 1920, 30
VERSE_CARD_SEC = 2.0   # 구절 카드를 읽을 시간. 쇼츠 피드의 썸네일 역할도 한다.
GAP_SEC = 0.4          # 문장 사이 간격

REQUIRED = ("topic", "ref", "verse_ko", "verse_en", "narration", "bg")


def load_script(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ValueError(f"{path.name}: 필드 누락 {missing}")
    if not isinstance(data["narration"], list) or not data["narration"]:
        raise ValueError(f"{path.name}: narration은 비어 있지 않은 문장 배열이어야 한다")
    if not (ROOT / data["bg"]).exists():
        raise FileNotFoundError(f"{path.name}: 배경 이미지 없음 {data['bg']}")
    return data


async def _tts(text: str, voice: str, out: Path):
    await edge_tts.Communicate(text=text, voice=voice).save(str(out))


def synth(text: str, voice: str, out: Path) -> float:
    """문장 하나를 음성으로 만들고 실제 재생 길이를 초 단위로 돌려준다."""
    asyncio.run(_tts(text, voice, out))
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(out)],
        capture_output=True, text=True, check=True,
    )
    return float(probe.stdout.strip())


def ass_time(sec: float) -> str:
    h, rem = divmod(max(sec, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_ass(segments: list[tuple[float, float, str]], path: Path):
    """자막 파일을 만든다. drawtext는 한글 자동 줄바꿈이 안 되므로 ASS를 쓴다."""
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,Malgun Gothic,64,&H00FFFFFF,&H00000000,&H80000000,1,1,4,2,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [
        f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Main,,0,0,0,,{t}"
        for a, b, t in segments
    ]
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


def build(script_path: Path) -> Path:
    data = load_script(script_path)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_mp4 = OUT_DIR / (script_path.stem + ".mp4")

    work = Path(tempfile.mkdtemp(prefix="kjvshorts_"))
    try:
        # 1. 무음 카드 + 각 문장 음성 생성
        silence = work / "000_silence.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", str(VERSE_CARD_SEC), "-q:a", "9", str(silence)],
            check=True, capture_output=True,
        )

        pieces = [(silence, VERSE_CARD_SEC, f"{data['verse_ko']}\\N\\N— {data['ref']}")]
        jobs = [(data["verse_en"], VOICE_EN), (data["verse_ko"], VOICE_KO)]
        jobs += [(s, VOICE_KO) for s in data["narration"]]

        for i, (text, voice) in enumerate(jobs, 1):
            mp3 = work / f"{i:03d}.mp3"
            dur = synth(text, voice, mp3)
            pieces.append((mp3, dur, text))

        # 2. 자막 타이밍은 실제 음성 길이로 정한다
        segments, t = [], 0.0
        for _mp3, dur, text in pieces:
            segments.append((t, t + dur, text))
            t += dur + GAP_SEC
        total = t

        write_ass(segments, work / "sub.ass")

        # 3. 음성을 순서대로 이어 붙인다 (사이에 GAP_SEC 무음)
        gap = work / "gap.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", str(GAP_SEC), "-q:a", "9", str(gap)],
            check=True, capture_output=True,
        )
        listing = []
        for mp3, _dur, _text in pieces:
            listing.append(f"file '{mp3.name}'")
            listing.append(f"file '{gap.name}'")
        (work / "concat.txt").write_text("\n".join(listing) + "\n", encoding="utf-8")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
             "-c", "copy", "audio.mp3"],
            cwd=work, check=True, capture_output=True,
        )

        # 4. Ken Burns 배경 + 자막 + 음성 -> MP4
        #    subtitles 필터는 Windows 절대경로의 콜론 이스케이프가 까다로우므로
        #    작업 디렉터리를 work로 두고 파일명만 넘긴다.
        shutil.copy(ROOT / data["bg"], work / "bg.jpg")
        vf = (
            f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,"
            f"crop={W*2}:{H*2},"
            f"zoompan=z='min(1+0.00035*on,1.18)'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={W}x{H}:fps={FPS},"
            f"subtitles=sub.ass"
        )
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-t", f"{total:.2f}", "-i", "bg.jpg",
             "-i", "audio.mp3", "-vf", vf,
             "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-shortest", str(out_mp4)],
            cwd=work, check=True,
        )
        return out_mp4
    finally:
        # 성공했을 때만 치운다. 실패하면 원인 추적을 위해 남긴다.
        if out_mp4.exists():
            shutil.rmtree(work, ignore_errors=True)
        else:
            print(f"작업 파일을 남겨 둠: {work}", file=sys.stderr)


def main():
    paths = [Path(a) for a in sys.argv[1:]]
    if not paths:
        print("usage: python build.py scripts/<name>.json [...]", file=sys.stderr)
        raise SystemExit(2)
    for p in paths:
        try:
            print(f"built {build(p)}")
        except Exception as e:
            # 대본 하나가 실패해도 나머지 배치는 계속 만든다
            print(f"FAILED {p.name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 예시 대본으로 실행**

Run: `python build.py scripts/example.json`
Expected: `built ...\out\example.mp4`

FFmpeg이 실패하면 stderr가 그대로 나오고 작업 폴더 경로가 출력된다. 그 폴더의 `sub.ass`와 `audio.mp3`를 직접 열어 확인한다.

- [ ] **Step 6: 결과 영상을 눈과 귀로 확인**

Run: `ffprobe -v error -show_entries stream=width,height,codec_name -of default=nw=1 out/example.mp4`
Expected: `codec_name=h264`, `width=1080`, `height=1920`, 그리고 `codec_name=aac`

그 다음 실제로 재생해서 확인한다:

```bash
start out/example.mp4
```

확인 항목: ①첫 2초에 구절이 크게 보이는가 ②한글 자막이 깨지지 않는가 ③자막과 음성이 맞는가 ④배경이 천천히 확대되는가

자막 글꼴이 깨지면 `write_ass`의 `Malgun Gothic`을 시스템에 설치된 다른 한글 글꼴로 바꾼다.

- [ ] **Step 7: 커밋**

```bash
git add build.py topics.json bg/README.md scripts/example.json
git commit -m "feat: render meditation shorts MP4 from script JSON"
```

---

### Task 6: 유튜브 예약 업로드

**Files:**
- Create: `upload.py`
- Modify: `bg/README.md` 옆에 `docs/youtube-setup.md` 생성

**Interfaces:**
- Consumes: `out/*.mp4` (Task 5), `client_secret.json` (사용자가 Google Cloud Console에서 내려받아 프로젝트 루트에 둔다), 같은 이름의 대본 JSON (제목·설명 생성용)
- Produces: 유튜브 비공개 예약 게시물. 다른 스크립트가 의존하지 않는 최종 단계다.

- [ ] **Step 1: OAuth 준비 문서 작성**

`docs/youtube-setup.md`:

```markdown
# 유튜브 업로드 최초 1회 설정

1. https://console.cloud.google.com 에서 프로젝트를 만든다.
2. "API 및 서비스" → "라이브러리" → **YouTube Data API v3** 사용 설정.
3. "OAuth 동의 화면"을 구성한다. 외부(External) + 테스트 사용자에 본인 계정 추가.
4. "사용자 인증 정보" → "OAuth 클라이언트 ID" → 유형 **데스크톱 앱**.
5. 내려받은 JSON을 프로젝트 루트에 `client_secret.json`으로 저장한다.

`upload.py`를 처음 실행하면 브라우저가 열리고 승인 절차가 진행된다.
승인 후 `token.json`이 저장되어 다음부터는 브라우저가 열리지 않는다.

`client_secret.json`과 `token.json`은 `.gitignore`에 있다. 절대 커밋하지 않는다.

## 할당량

기본 일일 할당량은 10,000 단위이고 업로드 1건이 약 1,600 단위를 쓴다.
하루 6건까지가 안전선이다. 주 2–3개 계획에는 여유가 있다.
```

- [ ] **Step 2: 업로드 스크립트 작성**

`upload.py`:

```python
"""완성된 MP4를 유튜브에 비공개 예약 업로드한다.

사람이 out/의 영상을 직접 확인한 뒤 명시적으로 실행하는 스크립트다.
어떤 자동 경로에서도 호출되지 않는다.
"""
import datetime as dt
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build as build_service
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).parent
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET = ROOT / "client_secret.json"
TOKEN = ROOT / "token.json"

CATEGORY_ID = "22"  # People & Blogs


def credentials() -> Credentials:
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not CLIENT_SECRET.exists():
            raise FileNotFoundError(
                f"{CLIENT_SECRET} 없음. docs/youtube-setup.md 참고."
            )
        creds = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET), SCOPES
        ).run_local_server(port=0)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def metadata(mp4: Path) -> tuple[str, str, list[str]]:
    """같은 이름의 대본 JSON에서 제목·설명을 만든다."""
    script = ROOT / "scripts" / (mp4.stem + ".json")
    if not script.exists():
        raise FileNotFoundError(f"대본 없음: {script}")
    d = json.loads(script.read_text(encoding="utf-8"))
    title = f"{d['ref']} | {d['topic']} #shorts"
    description = (
        f"{d['verse_ko']}\n— {d['ref']} (킹제임스 흠정역)\n\n"
        f"{d['verse_en']}\n— KJV\n\n"
        + "\n".join(d["narration"])
    )
    return title, description, ["킹제임스", "흠정역", "성경", d["topic"]]


def upload(mp4: Path, publish_at: dt.datetime):
    title, description, tags = metadata(mp4)
    youtube = build_service("youtube", "v3", credentials=credentials())
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title[:100],  # 유튜브 제목 상한
                "description": description[:5000],
                "tags": tags,
                "categoryId": CATEGORY_ID,
            },
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_at.astimezone(dt.timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "selfDeclaredMadeForKids": False,
            },
        },
        media_body=MediaFileUpload(str(mp4), chunksize=-1, resumable=True),
    )
    response = request.execute()
    print(f"uploaded: https://youtu.be/{response['id']}  (예약: {publish_at})")


def main():
    if len(sys.argv) < 2:
        print("usage: python upload.py out/<name>.mp4 [YYYY-MM-DDTHH:MM]", file=sys.stderr)
        raise SystemExit(2)
    mp4 = Path(sys.argv[1])
    if not mp4.exists():
        raise FileNotFoundError(mp4)
    when = (
        dt.datetime.fromisoformat(sys.argv[2])
        if len(sys.argv) > 2
        else dt.datetime.now() + dt.timedelta(days=1)
    )
    upload(mp4, when.astimezone())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 대본 없이 실행해 오류 처리 확인**

Run: `python upload.py out/nonexistent.mp4`
Expected: `FileNotFoundError: out\nonexistent.mp4` — 인증 절차로 들어가기 전에 멈춰야 한다.

- [ ] **Step 4: 실제 업로드는 사용자 승인 후에만**

이 단계는 **외부에 콘텐츠를 게시한다.** 실행 전 반드시 사용자에게 확인받는다.

Run: `python upload.py out/example.mp4`
Expected: 최초 1회 브라우저 승인 → `uploaded: https://youtu.be/...`

업로드 후 유튜브 스튜디오에서 비공개 상태이고 예약 시각이 설정되었는지 확인한다.

- [ ] **Step 5: 커밋**

```bash
git add upload.py docs/youtube-setup.md
git commit -m "feat: add scheduled YouTube upload with manual trigger"
```

---

### Task 7: 주간 작업 절차 문서화

파이프라인을 만든 사람과 매주 돌리는 사람이 같아도, 3주 뒤의 자신은 남이다.

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: 앞선 모든 태스크의 산출물
- Produces: 없음 (문서)

- [ ] **Step 1: README 작성**

`README.md`:

````markdown
# 킹제임스 묵상 쇼츠 파이프라인

킹제임스 흠정역 성경으로 유튜브 쇼츠를 반자동 제작한다.
설계 문서: `docs/superpowers/specs/2026-08-04-kjv-shorts-design.md`

## 최초 1회 준비

```bash
python -m pip install -r requirements.txt
python fetch_kjv_en.py      # 영어 KJV 내려받기
python parse_bible.py       # 흠정역 PDF -> bible/kjv_ko.json (검증 포함)
python extract_corpus.py    # 주석 PDF 109개 -> corpus/*.txt (몇 분 소요)
```

`bg/`에 세로 배경 이미지를 몇 장 넣는다. 유튜브 업로드 설정은 `docs/youtube-setup.md` 참고.

## 매주 작업

1. Claude Code에 이렇게 말한다:

   > 이번 주 쇼츠 3개 만들어줘

   Claude Code가 `topics.json`에서 다음 주제를 확인하고, `corpus/`를 grep해
   근거 자료를 참고하고, `bible/`에서 구절을 인용해 `scripts/`에 대본 JSON을 쓴다.

2. 영상을 만든다:

   ```bash
   python build.py scripts/2026-08-11-*.json
   ```

3. `out/`의 영상을 직접 본다. 마음에 들면 업로드한다:

   ```bash
   python upload.py out/2026-08-11-faith-01.mp4 2026-08-12T08:00
   ```

   마음에 안 들면 대본 JSON을 고치고 2번을 다시 돌린다.

## 주의

- `킹제임스 자료모음` 폴더는 읽기 전용이다. 원본 PDF를 수정하지 않는다.
- `bible/`, `corpus/`, `out/`은 커밋하지 않는다 (저작권·용량).
- `parse_bible.py`의 검증이 실패하면 JSON을 쓰지 않고 멈춘다. 무시하고 진행하지 않는다.
  잘못 파싱된 구절은 그대로 영상이 되어 공개된다.
````

- [ ] **Step 2: 문서대로 따라가며 빠진 단계가 없는지 확인**

README의 "최초 1회 준비"를 처음부터 그대로 실행해 본다. 중간에 설명되지 않은 수동 작업이 필요하면 README에 추가한다.

- [ ] **Step 3: 커밋**

```bash
git add README.md
git commit -m "docs: add weekly workflow README"
```

---

## Self-Review

**1. Spec coverage**

| 스펙 항목 | 담당 태스크 |
|---|---|
| §4 소스 데이터 | Task 2 (`BIBLE_PDF`), Task 4 (`SKIP`으로 성경 PDF 2종 제외) |
| §5.1 디렉터리 | Task 1·5 (생성), Task 7 (문서화) |
| §5.2 모듈 경계 | 각 스크립트가 파일로만 소통. `extract_corpus.py`가 `parse_bible.py`에서 경로 상수만 import — 로직 의존 없음 |
| §5.3 대본 JSON 스키마 | Task 5 `REQUIRED`, `load_script` |
| §5.4 topics.json | Task 5 Step 2 |
| §6 주간 흐름 | Task 7 README |
| §7.1–7.2 조판 구조 | Task 2 `classify_lines` |
| §7.3 단일 장 책·헤더 불규칙 | Task 3 `HEADER_LINE`이 장 번호 없는 헤더 허용, 테스트로 오바댜·빌레몬서 확인 |
| §7.4 순서로 권 대응 | Task 3 `book_short_names` + `expected[bi]` 인덱스 대응 |
| §7.5 본문 범위 | Task 3 `if bi >= 66: return` |
| §7.6 영어 KJV 검증 | Task 1 `fetch_kjv_en.py` assert, Task 3 `_validate` |
| §8.1 TTS | Task 5 `synth`, `VOICE_KO`/`VOICE_EN` |
| §8.2 ASS 자막 | Task 5 `write_ass` |
| §8.3 구성 순서 | Task 5 `pieces` 조립 순서 (카드 → 영어 → 한글 → 해설) |
| §8.4 영상 합성 | Task 5 `vf` (zoompan + subtitles) |
| §9 업로드 | Task 6 |
| §10 오류 처리 | Task 3 `_validate` 예외, Task 5 `load_script` 즉시 실패·배치 계속·작업 폴더 보존, Task 4 파일별 예외 격리 |
| §11 저작권 | Task 7 README 주의사항, `.gitignore` |
| §12 비목표 | 해당 태스크 없음 (의도적) |

빠진 스펙 항목 없음.

**2. Placeholder scan**

"TBD", "TODO", "적절히 처리", "위 내용에 대한 테스트 작성" 같은 표현 없음. 모든 코드 단계에 실제 코드 블록이 있고, 모든 실행 단계에 실제 명령과 기대 출력이 있다.

**3. Type consistency**

- `Line(text, verse_no)` — Task 2에서 정의, Task 3 `build_bible`에서 `line.verse_no is None` / `line.text`로 사용. 일치.
- `classify_lines(page) -> list[Line]` — Task 2 정의, Task 3 사용. 일치.
- `load_expected_structure() -> list[dict[int, int]]` — Task 3 정의. `_validate`에서 `want.items()`로 `{장번호: 절수}` 사용. 일치.
- `BIBLE_PDF`, `SOURCE_DIR` — Task 2 정의, Task 4에서 import. 일치.
- 대본 JSON 키 6개 — Task 5 `REQUIRED`, `scripts/example.json`, Task 6 `metadata()`에서 `d['ref']`, `d['topic']`, `d['verse_ko']`, `d['verse_en']`, `d['narration']` 사용. 일치.
- `bible/kjv_ko.json` 구조 `{권: {장: {절: 본문}}}` — Task 3 `build_bible` 생성, Task 3 Step 6 확인 명령에서 `b['창세기']['1']['1']`로 접근. 문자열 키로 일관.
