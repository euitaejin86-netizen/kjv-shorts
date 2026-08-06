# 세션 연속성 문서

**최종 갱신: 2026-08-06.** 새 Claude Code 세션이 이 프로젝트를 이어받을 때 먼저
읽을 문서. 컨텍스트 창이 가득 차서 대화가 요약/새 세션으로 넘어갈 때를 대비해
"코드와 git 로그에는 없지만 알아야 하는 것"만 적는다. 파이프라인 구조 자체는
[README.md](../README.md)와 [설계 문서](superpowers/specs/2026-08-04-kjv-shorts-design.md)에
이미 있으므로 여기서 반복하지 않는다.

## 지금 상태 한 줄 요약

파이프라인(파싱→대본→렌더링→업로드) 완성. 애니메이션·BGM·여러 배경 전환까지
구현 완료. 영상 2개 제작: 1개는 유튜브에 예약 게시됨, 1개는 렌더링만 하고
업로드 여부 대기 중.

## 지켜야 하는 규칙 (기억 파일에도 있음, 여기서도 강조)

- **주제·내용을 절대 임의로 정하지 않는다.** 매번 먼저 묻는다. (이 규칙은
  저장소 밖 기억 파일 `kjv-shorts-ask-before-choosing-topic.md`에도 있다 —
  `C:\Users\uieta\.claude\projects\...\memory\`. 매 세션 자동으로 불러와진다.)
- **성경 구절은 절대 기억으로 타이핑하지 않는다.** `bible/kjv_ko.json` /
  `kjv_en.json`에서 코드로 그대로 꺼내 쓰고, narration 안에서 직접 인용할 때도
  실제 JSON 값과 글자 단위로 대조 검증한다 (이번 세션에서 두 번 이걸로 실수를
  잡았다 — 말라기 4:6 오염, 21:27 인용 방향 실수).

## 지금까지 만든 영상

| 파일 | 주제 | 상태 |
|---|---|---|
| `scripts/2026-08-04-rapture-01.json` → `out/2026-08-04-rapture-01.mp4` | 데살로니가전서 4:17 (휴거) | **업로드 완료.** 비공개 예약, 공개 예정 2026-08-06 02:38 KST. https://youtu.be/NXJXcgZVu3I |
| `scripts/2026-08-05-tree-of-life-01.json` → `out/2026-08-05-tree-of-life-01.mp4` | 창세기 3:24 / 요한계시록 22:14 (생명나무, 새 예루살렘 시리즈 중 첫 편) | **업로드 완료.** 비공개 예약, 공개 예정 2026-08-07 17:24 KST. https://youtu.be/XPEOfuP3e00 · 3장면 전환(막힘→나무→열림) 배경 사용, 영/한 낭독 자막에 성경 주소 표시(`ref_display`) 적용판. |

## 다음 영상 후보 (사용자가 언급, 아직 미착수)

- **"천국에 대한 흔한 오해"** — 새 예루살렘 소재를 고르던 중 사용자가 직접 제안한
  다음 주제 후보. 아직 세부 각도 논의 전.
- 새 예루살렘 소재 자체가 큰 주제라 자료 조사 때 후보를 여럿 뽑아뒀다
  (크기, 빛의 근원, 눈물 없음 등). `corpus/천국과 지옥 바로 알기...`와
  `corpus/재림과 휴거 파노라마...`에 밀도 높게 있다.

## 이번 세션에서 build.py에 추가된 기능 (README에 이미 반영됨, 요약만)

1. 자막 페이드 인/아웃 (`SUB_FADE_MS`)
2. 배경음악 + 사이드체인 더킹 (`bgm` 선택 필드, `BGM_VOLUME`)
3. **배경 이미지 여러 장 지원** — `bg` 필드가 문자열 하나 또는 리스트를 받는다.
   리스트면 영상 길이를 장 수만큼 균등 분배해 순서대로 전환한다 (`bg_list`,
   `bg_segment_durations`).
4. 영/한 구절 낭독 자막에 성경 주소 표시 (`ref_display` — "창세기 3:24" →
   "창세기 3장 24절", 괄호 형식으로 화면에 표시)

테스트 35개, 전부 통과 상태로 각 기능 커밋됨 (`git log --oneline`으로 확인).

## 확보된 리소스

- `bg/`: `plain.jpg`(테스트용, git 추적됨), `rapture.jpg`, `project2_entrance.png`,
  `project2_entrance_sword.jpg`(미사용, 예비), `project2_tree.jpg`, `project2_tree2.jpg`
  — 전부 제미나이로 생성, git에는 안 올라감(`.gitignore`).
- `bgm/`: `amazing-grace-organ.mp3` (Wikimedia Commons, **CC BY-SA 2.5 — 저작자
  표시 필수**. 대본의 `credit` 필드에 이미 넣어뒀고 `upload.py`가 설명란에
  자동으로 붙인다). git에는 안 올라감.
- 유튜브 OAuth 완료: `client_secret.json`, `token.json` 둘 다 로컬에 존재
  (git에는 안 올라감). **Testing 모드라 토큰이 7일마다 만료** — 그때 되면
  `upload.py` 실행 시 브라우저가 자동으로 다시 뜬다. 정상 동작이니 당황하지 않는다.

## 환경 관련 주의사항

- **Git Bash로 `python build.py` 실행하면 세그멘테이션 폴트가 난다.** PowerShell로
  실행할 것. (`ffmpeg` 자체 문제로 추정, 원인 미확정.) 지금까지 렌더링은 전부
  PowerShell 도구로 했다.
- ffmpeg는 winget으로 설치됐고 사용자 PATH에 등록되어 있지만, 이 세션의 프로세스
  환경은 오래돼서 못 본다 — 절대 경로를 PATH에 prepend해서 쓰고 있다:
  `C:\Users\uieta\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin`
- 콘솔에 한글을 출력하면 mojibake로 깨져 보인다 — 표시 문제일 뿐 데이터는
  멀쩡하다. 확인할 땐 UTF-8 파일로 써서 Read 도구로 읽는다.

## 배경음악 관련 미해결 논의

Amazing Grace 오르간(33초)이 90초 영상 내내 반복 재생되는데, 반복이 티가 나는지
사용자에게 아직 확인 안 받음. 짧은 곡을 계속 쓸지, 더 긴 곡을 구할지는 열려 있다.
