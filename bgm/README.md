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

CC BY-SA처럼 저작자 표시가 필요한 곡을 쓰면, 업로드 시 영상 설명란에 아래 크레딧을
반드시 넣는다 (`upload.py`가 `scripts/*.json`에서 설명을 자동 생성하므로, 크레딧이
필요한 곡을 쓴 주에는 그 대본의 `narration` 끝이나 별도 필드로 직접 챙겨 넣는다).

- **`amazing-grace-organ.mp3`** — Amazing Grace, 오르간 독주.
  출처: [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Amazing_Grace-organ.ogg)
  (업로더 UninvitedCompany, 2005년). 라이선스: **CC BY-SA 2.5** — 영상 설명에
  "Amazing Grace (organ) by UninvitedCompany, CC BY-SA 2.5,
  commons.wikimedia.org/wiki/File:Amazing_Grace-organ.ogg" 한 줄 필요.
  원본은 33초라 자동으로 반복 재생된다.
