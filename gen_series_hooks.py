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
    elif "url" in img:
        print("URL:", img["url"])
    return out

# #2 오해받는 말씀 - 인지부조화 (성경 + 갈림길)
gen(
    "Vertical 9:16 cinematic image for a Korean Bible shorts hook titled 'the most misunderstood verse'. "
    "An open Bible at the center whose pages split into two diverging paths of light, symbolizing two opposite interpretations "
    "people take from the same verse. One path is dim/cold, the other path is warm golden light. "
    "A subtle large questionremoved mark shape formed by the light paths. Deep dark moody background, solemn, mysterious. "
    "Large clean dark negative space in bottom two-thirds for on-screen text. Photorealistic, high contrast, cinematic lighting. "
    "No people, no faces, no text, no watermark.",
    r"C:\Users\uieta\KEEPBIBLE\kjv-shorts\bg\hook_misunderstood_verse.png"
)

# #3 한 절이 당신을 바꾼다 - 어둠에서 빛으로
gen(
    "Vertical 9:16 cinematic image for a Korean Bible shorts hook titled 'this one verse will change you'. "
    "A dramatic dark valley of shadows in the background, and in the foreground a single glowing path of warm golden light "
    "leading forward, as if inviting the viewer to step out of darkness into light. A subtle silhouette of feet about to step "
    "onto the lit path. Deep dark moody atmosphere, scattered golden light motes, hopeful and solemn. "
    "Large clean dark negative space in bottom two-thirds for on-screen text. Photorealistic, high contrast, cinematic. "
    "No faces, no readable text, no watermark.",
    r"C:\Users\uieta\KEEPBIBLE\kjv-shorts\bg\hook_valley_to_light.png"
)
print("DONE")