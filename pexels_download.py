import json, urllib.request, urllib.parse, time, subprocess, sys
from pathlib import Path

def read_key(env_path, prefix):
    for line in Path(env_path).read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if s.startswith(prefix):
            return s.split('=', 1)[1].strip().strip('"').strip("'")
    return None

key = read_key(Path.home()/'.hermes'/'.env', 'PEXELS_API_KEY')
if not key:
    sys.exit('no pexels key')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36'
BG = Path(r'C:\Users\uieta\KEEPBIBLE\kjv-shorts\bg\video')

def search(term, per=10):
    url = 'https://api.pexels.com/v1/videos/search?query=%s&orientation=portrait&per_page=%d' % (urllib.parse.quote(term), per)
    req = urllib.request.Request(url, headers={'Authorization': key, 'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.loads(r.read().decode())
    out = []
    for v in d.get('videos', []):
        files = [f for f in v.get('video_files', []) if f.get('width')==1080 and f.get('height')==1920]
        files = files or sorted(v.get('video_files', []), key=lambda f:(f.get('width') or 0)*(f.get('height') or 0), reverse=True)
        if files:
            out.append((v['id'], files[0]['link'], v['url']))
    return out

# (로컬이름, 검색어, 원하는 결과 인덱스) — 검색어별 훑어서 고른 것
wanted = {
    'book_pages':      ('open old bible', 0),
    'hebrew_bible':    ('hebrew bible', 0),
    'sun_over_clouds': ('sun over clouds aerial', 0),
    'shepherd_golden': ('shepherd flock countryside', 1),
    'dove':            ('dove flying', 0),
    'olive_grove':     ('olive trees', 0),
    'sunrays_window':  ('sunrays through window church', 0),
    'candle_serene':   ('candle flame dark', 2),
    'church_light':    ('church interior light', 0),
    'shepherd_flock':  ('shepherd sheep field', 1),
}

for name, (term, idx) in wanted.items():
    try:
        res = search(term)
        if not res:
            print('%s: no results' % name); continue
        # idx 클램프
        if idx >= len(res): idx = len(res)-1
        vid, link, page = res[idx]
        dst = BG / ('%s_%d.mp4' % (name, vid))
        # curl로 다운로드 (UA+referer)
        cmd = ['curl', '-sL', '-A', UA, '-e', 'https://www.pexels.com/', '-o', str(dst), link]
        subprocess.run(cmd, check=True)
        sz = dst.stat().st_size
        print('%s: %s <- id=%s (%d KB)' % (name, dst.name, vid, sz//1024))
    except Exception as e:
        print('%s ERR %s' % (name, e))
    time.sleep(0.4)

print('DONE')