"""완성된 MP4를 유튜브에 비공개 예약 업로드한다.

사람이 out/의 영상을 직접 확인한 뒤 명시적으로 실행하는 스크립트다.
어떤 자동 경로에서도 호출되지 않는다.
"""
import datetime as dt
import json
import sys
from pathlib import Path

from google.auth.exceptions import RefreshError
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

REQUIRED = ("ref", "topic", "verse_ko", "verse_en", "narration")


def credentials() -> Credentials:
    creds = None
    if TOKEN.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        except ValueError as e:
            print(f"{TOKEN} 손상됨 ({e}); 다시 로그인합니다.", file=sys.stderr)
            creds = None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            print(f"토큰 갱신 실패 ({e}); 다시 로그인합니다.", file=sys.stderr)
            creds = None
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
    missing = [k for k in REQUIRED if k not in d]
    if missing:
        raise ValueError(f"{script.name}: 필드 누락 {missing}")
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
        print(
            "usage: python upload.py out/<name>.mp4 [YYYY-MM-DDTHH:MM]\n"
            "  생략 시 지금부터 24시간 뒤(로컬 시간대)로 예약된다.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    mp4 = Path(sys.argv[1])
    if not mp4.exists():
        raise FileNotFoundError(mp4)
    if len(sys.argv) > 2:
        try:
            when = dt.datetime.fromisoformat(sys.argv[2])
        except ValueError:
            raise ValueError(
                f"시간 형식 오류: {sys.argv[2]!r}. 예: 2026-08-05T09:00"
            ) from None
    else:
        when = dt.datetime.now() + dt.timedelta(days=1)
    upload(mp4, when.astimezone())


if __name__ == "__main__":
    main()
