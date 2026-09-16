"""Veo quality test — 8s 9:16 cinematic Bible background clip."""
import os, time, sys
from pathlib import Path
from google import genai
from google.genai import types


def load_key():
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.getenv(name):
            return os.environ[name]
    for p in (Path.home()/".hermes"/".env", Path(".env")):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                if s.startswith(name+"=") and s.split("=",1)[1].strip():
                    return s.split("=",1)[1].strip().strip('"').strip("'")
    raise RuntimeError("Gemini API key not found")


MODEL = "veo-3.1-fast-generate-preview"
OUT = Path("out/veo_test_01.mp4")

PROMPT = (
    "Cinematic 9:16 vertical video background for a Bible verse short. "
    "An ancient open Bible resting on dark aged wood, pages gently turning in a slow breeze, "
    "warm golden candlelight flickering from the side, soft rays of divine light falling from above, "
    "dark atmospheric background with clean negative space in the center for captions. "
    "Photorealistic, moody, reverent, slow camera push-in, no people, no faces, no text, no watermark."
)

def main():
    client = genai.Client(api_key=load_key())
    print("requesting", MODEL, "...")
    op = client.models.generate_videos(
        model=MODEL,
        prompt=PROMPT,
        config=types.GenerateVideosConfig(
            aspect_ratio="9:16",
            duration_seconds=8,
            resolution="1080p",
            number_of_videos=1,
        ),
    )
    t0 = time.time()
    while not op.done:
        time.sleep(10)
        op = client.operations.get(op)
        print(f"  ...polling {time.time()-t0:.0f}s done={op.done}")
    print("operation done in", round(time.time()-t0, 1), "s")
    try:
        vids = op.result.generated_videos
    except Exception as e:
        print("error reading result:", e)
        print("operation:", op)
        sys.exit(1)
    if not vids:
        print("no videos in result")
        sys.exit(1)
    vid = vids[0]
    print("video uri:", getattr(vid.video, "uri", None))
    OUT.parent.mkdir(exist_ok=True)
    client.files.download(file=vid.video, path=str(OUT))
    print("saved:", OUT, OUT.stat().st_size, "bytes")

if __name__ == "__main__":
    main()
