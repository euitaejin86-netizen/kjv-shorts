import json, urllib.request, base64, sys
from pathlib import Path

def read_key(env_path, prefix):
    for line in Path(env_path).read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if s.startswith(prefix):
            return s.split('=', 1)[1].strip().strip('"').strip("'")
    return None

key = read_key(Path.home()/'.hermes'/'.env', 'OPENROUTER_API_KEY')
if not key:
    sys.exit('no openrouter key')

prompt = (
    "Vertical 9:16 cinematic image for a Korean Bible shorts video hook. "
    "A dramatic conceptual contrast that sparks curiosity: an ancient weathered Bible located "
    "inside a dark museum glass display case with a soft cold spotlight (representing 'a locked-away word'), "
    "while in the foreground an open Bible glows with warm golden radiant light (representing 'the living word "
    "in hand'). Strong tension between cold museum preservation and warm alive faith. "
    "Deep dark moody background, soft golden light rays, subtle floating light particles, solemn and mysterious. "
    "Large clean dark negative space in the bottom two-thirds reserved for on-screen text. "
    "Photorealistic, high contrast, cinematic lighting. No people, no faces, no text, no watermark."
)

payload = {
    "model": "openai/gpt-image-2",
    "prompt": prompt,
    "n": 1,
    "size": "1024x1792",
}
req = urllib.request.Request(
    "https://openrouter.ai/api/v1/images/generations",
    data=json.dumps(payload).encode(),
    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=180) as r:
    data = json.loads(r.read().decode())

img = data["data"][0]
out = Path(r"C:\Users\uieta\KEEPBIBLE\kjv-shorts\bg\hook_museum_vs_hand.png")
if "b64_json" in img:
    out.write_bytes(base64.b64decode(img["b64_json"]))
    print("saved", out, out.stat().st_size//1024, "KB")
elif "url" in img:
    print("URL:", img["url"])
else:
    print("keys:", list(img.keys()), json.dumps(data)[:500])