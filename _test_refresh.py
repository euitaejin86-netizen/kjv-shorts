from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

TOKEN = Path("token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
print("has refresh_token:", bool(creds.refresh_token))
print("expired:", creds.expired)
print("valid:", creds.valid)

try:
    creds.refresh(Request())
    print("REFRESH OK - token alive")
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    print("token.json updated")
except Exception as e:
    print("REFRESH FAIL:", type(e).__name__, str(e)[:300])
