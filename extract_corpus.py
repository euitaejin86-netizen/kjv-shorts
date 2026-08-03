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
    import sys
    print(f"{len(pdfs)} PDFs to extract")

    for i, pdf in enumerate(sorted(pdfs), 1):
        out = OUT_DIR / (pdf.stem + ".txt")
        if out.exists():
            continue  # 중단 후 재실행할 수 있게 이미 뽑은 것은 건너뛴다
        try:
            with fitz.open(pdf) as doc:
                text = "\n".join(page.get_text() for page in doc)
            out.write_text(text, encoding="utf-8")
            try:
                print(f"[{i}/{len(pdfs)}] {pdf.name} -> {len(text):,} chars")
            except UnicodeEncodeError:
                sys.stdout.buffer.write(f"[{i}/{len(pdfs)}] {pdf.name} -> {len(text):,} chars\n".encode("utf-8", errors="replace"))
        except Exception as e:
            # 한 파일이 깨져도 나머지 108개는 계속 뽑는다
            try:
                print(f"[{i}/{len(pdfs)}] FAILED {pdf.name}: {e}")
            except UnicodeEncodeError:
                sys.stdout.buffer.write(f"[{i}/{len(pdfs)}] FAILED {pdf.name}: {e}\n".encode("utf-8", errors="replace"))


if __name__ == "__main__":
    main()
