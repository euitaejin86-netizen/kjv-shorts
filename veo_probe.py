from pathlib import Path
import os
from google import genai


def load_key():
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.getenv(name):
            return os.environ[name]
    for p in (Path.home()/".hermes"/".env", Path(".env")):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            s=line.strip()
            for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                if s.startswith(name+"=") and s.split("=",1)[1].strip():
                    return s.split("=",1)[1].strip().strip('"').strip("'")
    raise RuntimeError("Gemini API key not found")

client=genai.Client(api_key=load_key())
for m in client.models.list():
    name=getattr(m, "name", "") or ""
    actions=" ".join(getattr(m, "supported_actions", None) or [])
    text=(name+" "+actions).lower()
    if "veo" in text or "video" in text or "omni" in text:
        print(name, "|", actions)
