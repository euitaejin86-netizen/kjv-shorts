import json, urllib.request, time
from pathlib import Path

def read_key(env_path, prefix):
    for line in Path(env_path).read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if s.startswith(prefix):
            return s.split('=', 1)[1].strip().strip('"').strip("'")
    return None

key = read_key(Path.home()/'.hermes'/'.env', 'PEXELS_API_KEY')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36'

def video_files(vid):
    req = urllib.request.Request('https://api.pexels.com/v1/videos/%d' % vid,
                                 headers={'Authorization': key, 'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.loads(r.read().decode())
    files = [f for f in d.get('video_files', []) if f.get('width')==1080 and f.get('height')==1920]
    files = files or sorted(d.get('video_files', []), key=lambda f:(f.get('width') or 0)*(f.get('height') or 0), reverse=True)
    if not files:
        return None
    return files[0]['link'], d.get('url'), d.get('duration')

picks = {
    'book_pages': 11384843,
    'hebrew_bible': 5986566,
    'sun_over_clouds': 12278131,
    'shepherd_golden': 39096538,
    'dove': 27926031,
    'olive_grove': 26964399,
    'sunrays_window': 7568881,
    'candle_serene': 35133765,
    'church_light': 16668211,
    'shepherd_flock': 37979278,
}
out = {}
for name, vid in picks.items():
    try:
        r = video_files(vid)
        if r:
            out[name] = (vid, r[0], r[1], r[2])
            print('%s: id=%s dur=%ss %s' % (name, vid, r[2], r[1]))
        else:
            print('%s: no 1080x1920' % name)
    except Exception as e:
        print('%s err %s' % (name, e))
    time.sleep(0.35)

Path('/tmp/pexels_picks.json').write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
print('saved', len(out))