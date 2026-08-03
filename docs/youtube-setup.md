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
