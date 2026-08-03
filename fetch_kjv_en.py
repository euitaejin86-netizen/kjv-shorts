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
