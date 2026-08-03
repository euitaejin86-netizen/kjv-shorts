# 킹제임스 묵상 쇼츠 파이프라인

킹제임스 흠정역 성경으로 유튜브 쇼츠를 반자동 제작한다.
설계 문서: `docs/superpowers/specs/2026-08-04-kjv-shorts-design.md`

## 핵심 원칙

대본 JSON의 `verse_ko` / `verse_en`은 항상 `bible/kjv_ko.json`, `bible/kjv_en.json`에서
그대로 가져온 값이어야 한다. **성경 구절을 기억으로 타이핑하지 않는다.**
`parse_bible.py`의 검증이 존재하는 이유도 이 신뢰를 지키기 위해서다 — 검증이 실패하면
JSON을 쓰지 않고 그 자리에서 멈춘다. 무시하고 진행하면 잘못 파싱된 구절이 그대로
영상이 되어 공개된다.

## 최초 1회 준비

1. 의존성 설치

   ```bash
   python -m pip install -r requirements.txt
   ```

2. FFmpeg 확인

   ```bash
   ffmpeg -version
   ffprobe -version
   ```

   없다면:

   ```bash
   winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
   ```

   설치 직후에는 **새 터미널을 열어야 한다** — 설치 전에 이미 열려 있던 터미널은
   PATH가 갱신된 것을 보지 못한다.

3. 성경 데이터 준비 (반드시 이 순서로)

   ```bash
   python fetch_kjv_en.py      # 영어 KJV 다운로드 -> bible/kjv_en.json
   python parse_bible.py       # 흠정역 PDF -> bible/kjv_ko.json (영어 KJV와 대조 검증)
   python extract_corpus.py    # 주석·강해 PDF 115개 -> corpus/*.txt (몇 분 소요)
   ```

   `parse_bible.py`는 `bible/kjv_en.json`을 정답지로 검증에 쓰므로 `fetch_kjv_en.py`가
   먼저 끝나 있어야 한다. (원본 폴더에는 PDF가 117개 있고, 그중 성경 본문 PDF 자신과
   구판 성경 PDF 1종은 코퍼스에서 제외되어 115개만 추출된다.)

4. `bg/`에 세로(1080×1920 이상) 배경 이미지를 몇 장 넣는다. 자세한 안내는
   `bg/README.md` 참고. 넣지 않아도 예시 대본(`scripts/example.json`)은 테스트용
   `bg/plain.jpg`로 바로 돌려볼 수 있다.

5. 유튜브 업로드는 최초 실행 전에 한 번 Google Cloud Console 설정이 필요하다:
   `docs/youtube-setup.md` 참고.

## 매주 작업

1. Claude Code에 이렇게 말한다:

   > 이번 주 쇼츠 3개 만들어줘

   Claude Code가 `topics.json`에서 다음 주제를 확인하고(사용 후 `next` 갱신),
   `corpus/`를 grep해 근거 자료를 참고하고, `bible/kjv_ko.json` / `bible/kjv_en.json`에서
   구절을 그대로 인용해 `scripts/`에 대본 JSON을 쓴다.

   대본 JSON 스키마 (`build.py`가 이 6개 키를 검사한다):

   ```json
   {
     "topic": "믿음",
     "ref": "히브리서 11:1",
     "verse_ko": "한편 믿음은 바라는 것들의 실체요 보이지 않는 것들의 증거니",
     "verse_en": "Now faith is the substance of things hoped for, the evidence of things not seen.",
     "narration": ["문장 1.", "문장 2.", "문장 3."],
     "bg": "bg/plain.jpg"
   }
   ```

2. 영상을 만든다:

   ```bash
   python build.py scripts/2026-08-11-*.json
   ```

   대본 하나가 실패해도 나머지는 계속 만든다. (PowerShell에서 실행 중이라면 `*`가
   자동으로 펼쳐지지 않아 이 명령이 그대로 실패한다 — Git Bash를 쓰거나 파일명을
   하나씩 나열한다.)

3. `out/`의 영상을 직접 본다. 마음에 들면 업로드한다:

   ```bash
   python upload.py out/2026-08-11-faith-01.mp4 2026-08-12T08:00
   ```

   두 번째 인자(예약 시각)를 생략하면 지금부터 24시간 뒤, **이 컴퓨터의 로컬
   시간대**로 예약된다. 최초 실행 시에는 브라우저가 열려 로그인 승인을 요구한다
   (`docs/youtube-setup.md` 참고). 마음에 안 들면 대본 JSON을 고치고 2번을 다시 돌린다.

   스케줄러나 썸네일 자동 생성은 의도적으로 두지 않았다 — 영상을 직접 보고
   판단하는 단계가 파이프라인의 핵심이다.

## 주의

- `킹제임스 자료모음` 폴더는 읽기 전용이다. 원본 PDF를 수정하지 않는다.
- `bible/`, `corpus/`, `out/`, `bg/` 안의 이미지는 커밋하지 않는다 (저작권·용량,
  `.gitignore`에 이미 반영되어 있다).
- `client_secret.json`, `token.json`도 커밋하지 않는다 (`.gitignore`에 반영됨).
- `parse_bible.py`의 검증이 실패하면 JSON을 쓰지 않고 멈춘다. 무시하고 진행하지 않는다.
  잘못 파싱된 구절은 그대로 영상이 되어 공개된다.
