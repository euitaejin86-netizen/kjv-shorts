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

# build.py의 REQUIRED와 같은 대본 스키마를 검사한다 (build.py는 렌더링에
# "bg"가 더 필요해 이 목록에 "bg"가 하나 더 있다). 두 파일은 서로 import하지
# 않으므로(모듈 경계) 상수를 공유하지 않는다 — 필드를 바꾸면 이 파일과
# build.py:29 둘 다 고친다.
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
    # 다절 통합본(verses)과 단일 대본(verse_ko/verse_en/narration) 모두 지원한다.
    if d.get("verses") is not None:
        if not isinstance(d["verses"], list) or not d["verses"]:
            raise ValueError(f"{script.name}: verses는 비어 있지 않은 배열이어야 한다")
        # 제목은 전체 topic, 설명은 각 절(흠정역 한글 + KJV 영문)과 해설을 순서대로 이어 붙인다.
        title = f"{d['topic']} #shorts"
        parts = []
        for i, blk in enumerate(d["verses"]):
            bm = [k for k in ("ref", "verse_ko", "verse_en", "narration") if k not in blk]
            if bm:
                raise ValueError(f"{script.name}: verses[{i}] 필드 누락 {bm}")
            parts.append(
                f"{blk['verse_ko']}\n— {blk['ref']} (킹제임스 흠정역)\n\n"
                f"{blk['verse_en']}\n— KJV\n\n"
                + "\n".join(blk["narration"])
            )
        description = "\n\n".join(parts)
    else:
        missing = [k for k in ("topic", "ref", "verse_ko", "verse_en", "narration") if k not in d]
        if missing:
            raise ValueError(f"{script.name}: 필드 누락 {missing}")
        if not isinstance(d["narration"], list) or not d["narration"]:
            raise ValueError(f"{script.name}: narration은 비어 있지 않은 문장 배열이어야 한다")
        title = f"{d['ref']} | {d['topic']} #shorts"
        description = (
            f"{d['verse_ko']}\n— {d['ref']} (킹제임스 흠정역)\n\n"
            f"{d['verse_en']}\n— KJV\n\n"
            + "\n".join(d["narration"])
        )
    # "credit"은 선택 필드다. 저작자 표시가 필요한 배경음악을 쓴 대본에
    # 붙여 두면, 사람이 업로드 시 크레딧 넣는 걸 깜빡해도 여기서 자동으로 실린다.
    if d.get("credit"):
        description += f"\n\n{d['credit']}"
    return title, description, ["킹제임스", "흠정역", "성경", d["topic"]]


def upload(mp4: Path, publish_at: dt.datetime | None = None):
    """MP4를 유튜브에 업로드한다.

    publish_at이 None이면 즉시 공개(public), 있으면 그 시각으로 private 예약.
    """
    title, description, tags = metadata(mp4)
    youtube = build_service("youtube", "v3", credentials=credentials())
    status = {
        "privacyStatus": "private" if publish_at else "public",
        "selfDeclaredMadeForKids": False,
    }
    if publish_at:
        status["publishAt"] = publish_at.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title[:100],  # 유튜브 제목 상한
                "description": description[:5000],
                "tags": tags,
                "categoryId": CATEGORY_ID,
            },
            "status": status,
        },
        media_body=MediaFileUpload(str(mp4), chunksize=-1, resumable=True),
    )
    response = request.execute()
    vid = f"https://youtu.be/{response['id']}"
    if publish_at:
        print(f"uploaded: {vid}  (예약: {publish_at})")
    else:
        print(f"uploaded: {vid}  (공개 등록)")


def main():
    if len(sys.argv) < 2:
        print(
            "usage: python upload.py out/<name>.mp4 [YYYY-MM-DDTHH:MM | public]\n"
            "  public   → 즉시 공개 등록 (자동화에서 사용)\n"
            "  시간 생략 → 지금부터 24시간 뒤로 예약 (private)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    mp4 = Path(sys.argv[1])
    if not mp4.exists():
        raise FileNotFoundError(mp4)
    if len(sys.argv) > 2:
        if sys.argv[2] == "public":
            upload(mp4, None)
            return
        try:
            when = dt.datetime.fromisoformat(sys.argv[2])
        except ValueError:
            raise ValueError(
                f"시간 형식 오류: {sys.argv[2]!r}. 예: 2026-08-05T09:00 또는 public"
            ) from None
    else:
        when = dt.datetime.now() + dt.timedelta(days=1)
    upload(mp4, when.astimezone())


if __name__ == "__main__":
    main()
