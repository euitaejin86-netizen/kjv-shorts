"""원격 OAuth 재인증 스크립트 (refresh_token 재발급 전용).

업로드 토큰이 invalid_grant(expired/revoked)로 죽었을 때, GEEKOM에 직접
브라우저를 띄우지 않고 형이 어느 기기에서든 브라우저로 승인할 수 있게 한다.

사용법:
  1) python reauth.py url
       -> 승인 URL 출력. 형이 브라우저로 열어 계정 승인.
  2) 승인 후 브라우저 주소창이 http://localhost/?code=XXXX 로 이동하면
     (페이지는 연결 안 돼도 됨) 주소창의 code= 뒷부분을 복사.
  3) python reauth.py exchange <CODE>
       -> refresh_token 포함 새 token.json 저장. 이제 업로드 정상.
"""
import json
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).parent
CLIENT = json.loads((ROOT / "client_secret.json").read_text(encoding="utf-8"))["installed"]
CLIENT_SECRET = CLIENT["client_secret"]
TOKEN_URI = CLIENT["token_uri"]
SCOPE = "https://www.googleapis.com/auth/youtube.upload"
REDIRECT = "http://localhost"  # client_secret.json의 redirect_uris[0]와 일치해야 함


def auth_url() -> str:
    qs = urlencode({
        "client_id": CLIENT["client_id"],
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",   # refresh_token 받기
        "prompt": "consent",        # 매번 동의 화면 띄워 refresh_token 보장
    })
    return f"{CLIENT['auth_uri']}?{qs}"


def exchange(code: str):
    r = requests.post(TOKEN_URI, data={
        "client_id": CLIENT["client_id"],
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT,
    })
    data = r.json()
    if "refresh_token" not in data:
        print("EXCHANGE FAIL:", data)
        return 1
    token = {
        "token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "token_uri": TOKEN_URI,
        "client_id": CLIENT["client_id"],
        "client_secret": CLIENT_SECRET,
        "scopes": [SCOPE],
        "universe_domain": "googleapis.com",
        "account": "",
        "expiry": None,
    }
    (ROOT / "token.json").write_text(json.dumps(token), encoding="utf-8")
    print("EXCHANGE OK - new refresh_token saved to token.json")
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "url":
        url = auth_url()
        print("OPEN THIS URL IN YOUR BROWSER:\n", url)
        try:
            webbrowser.open(url)
            print("(브라우저 자동 열기 시도 - 열렸으면 무시)")
        except Exception:
            pass
    elif cmd == "exchange":
        if len(sys.argv) < 3:
            print("usage: python reauth.py exchange <CODE>")
            return 2
        return exchange(sys.argv[2])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())