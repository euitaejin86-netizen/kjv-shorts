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

def gen(prompt, out_path, size="1024x1792"):
    payload = {"model": "openai/gpt-image-2", "prompt": prompt, "n": 1, "size": size}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/images/generations",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read().decode())
    img = data["data"][0]
    out = Path(out_path)
    if "b64_json" in img:
        out.write_bytes(base64.b64decode(img["b64_json"]))
        print("saved", out.name, out.stat().st_size//1024, "KB")
        return out
    elif "url" in img:
        print("URL:", img["url"])
    return out

gen(
    "Vertical 9:16 cinematic image for a Korean Bible shorts hook about the deity of Christ. "
    "A radiant heavenly throne of light high in the background, and in the foreground an open ancient Bible "
    "with soft golden beams of glory streaming up from its pages toward the light, symbolizing God the Father "
    "calling the Son by the name of God. Deep dark moody background, solemn, majestic, awe-inspiring. "
    "Large clean dark negative space in the bottom two-thirds for on-screen text. Photorealistic, high contrast, cinematic lighting. "
    "No people, no faces, no text, no watermark.",
    r"C:\Users\uieta\KEEPBIBLE\kjv-shorts\bg\hook_christ_deity.png"
)
print("DONE")