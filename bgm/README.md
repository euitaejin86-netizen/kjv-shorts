# 배경음악

mp3 파일을 여기에 넣는다.

대본 JSON의 `bgm` 필드(선택)가 이 폴더의 파일을 가리킨다 (예: `"bgm": "bgm/calm.mp3"`).
`bgm`을 안 쓰면 배경음악 없이 렌더링된다 — 기존 대본은 손댈 필요 없다.

내레이션이 나오는 동안 배경음악은 자동으로 낮아진다(더킹). 곡 길이가 영상보다
짧으면 반복 재생되고 영상 길이에 맞춰 잘린다. 별도로 자르거나 루프를 만들 필요 없다.

## 어디서 받나

유튜브는 배경음악에 Content ID가 걸리면 수익화 여부와 무관하게 영상이 내려가거나
소유권 분쟁이 붙을 수 있다. 아래 순서로 확인한다.

1. **[유튜브 오디오 보관함](https://studio.youtube.com)** (YouTube Studio 안) — 가장 안전하다.
   Content ID 클레임이 구조적으로 걸리지 않는다.
2. **Pixabay Music** — 대체로 안전하지만, 일부 곡은 작곡가가 자기 곡을 Content ID에
   등록해 둬서 나중에 클레임이 걸리는 사례가 있다. 받은 뒤 라이선스 확인서를 저장해 둔다.

효과음(SFX)이 필요해지면 [freesound.org](https://freesound.org)에서 **CC0 라이선스만**
필터링해서 받는다.

매 실행마다 새로 내려받지 않는다. 몇 곡 받아두고 주제 분위기에 맞춰 고른다.

## 보유 곡 (라이선스·출처 기록)

**사용 원칙:** 유튜브 쇼츠 배경음악이 목적이므로 **수익화(Content ID) 리스크가 없는 곡**만 쓴다.
**이 폴더의 8곡은 전부 YouTube 오디오 라이브러리에서 받았다.** 오디오 라이브러리 곡은
크레딧 불필요 + Content ID 클레임 불가이므로, 수익화에 안전하다. (그래도 관례상 각 대본의
`credit` 필드에 곡명·작곡가를 남겨두면 나중에 소급 추적이 쉽다.) 오디오 라이브러리 밖의
CC BY 곡을 나중에 쓸 땐 크레딧을 영상 설명란에 반드시 넣는다.

### ✅ 기본 사용 곡 (solemn worship 계열)
- **`Prelude No. 12 - Chris Zabriskie.mp3` ← 현재 기본 BGM** — Prelude No. 12 (Chris Zabriskie).
  잔잔한 피아노 솔로, 명상·묵상 분위기, 나레이션을 방해하지 않는다. 61초.
  JSON `bgm` 값: `"bgm/Prelude No. 12 - Chris Zabriskie.mp3"`
  출처: YouTube 오디오 라이브러리. 크레딧 불필요.
  (대본 `credit`엔 "Music: Prelude No. 12 by Chris Zabriskie (YouTube Audio Library)" 표기함.)

### 🎯 예비 곡
- **`Lone Harvest - Kevin MacLeod.mp3`** — Lone Harvest (Kevin MacLeod). 차분한 포크/현악, 묵상에
  적합. 출처: YouTube 오디오 라이브러리. 크레딧 불필요. 60초.

### ⚠️ 비추천 (예배 쇼츠엔 부적합 또는 라이선스 불확실)
- **`An Upsetting Theme - The Descent - Kevin MacLeod.mp3`** — 호러/불안 분위기. 부적합.
- **`Comfortable Mystery 3 - Film Noire - Kevin MacLeod.mp3`** — 탐정/누아르 풍. 부적합.
- **`Troubled Bridges - Audionautix.mp3`** — 기타+신스 리듬, 나레이션 방해. 보통.
- **`Auld Lang Syne - The U.S. Army Band.mp3`** — 새해·이별 연상. 보통.
- **`Taps Bugle Call - The U.S. Army Band.mp3`** — 군 장례·취침 신호 연상. 라이선스는 안전(Public Domain)하나 맥락 부적합.
- **`Rapid_Unscheduled_Disassembly_The_Grey_Room_Density_&_Time.mp3`** — 전자음악 + 라이선스 불확실(Content ID 리스크). 부적합.

### 🚫 보류 (수익에 리스크)
- **`amazing-grace-organ.mp3`** — CC BY-SA 2.5. Content ID 클레임 위험. 더 이상 기본으로
  쓰지 않는다. 과거 대본엔 남아 있지만 새 영상에선 미사용 권장.
