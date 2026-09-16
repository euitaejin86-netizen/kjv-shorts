import json, urllib.request, urllib.parse, time, sys
from pathlib import Path

def read_key(env_path, prefix):
    for line in Path(env_path).read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if s.startswith(prefix):
            return s.split('=', 1)[1].strip().strip('"').strip("'")
    return None

if __name__ == '__main__':
    key = read_key(Path.home()/'.hermes'/'.env', 'PEXELS_API_KEY')
    if not key:
        sys.exit('no pexels key')
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36'

    def search(term, per=8):
        url = 'https://api.pexels.com/v1/videos/search?query=%s&orientation=portrait&per_page=%d' % (urllib.parse.quote(term), per)
        req = urllib.request.Request(url, headers={'Authorization': key, 'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read().decode())
        out = []
        for v in d.get('videos', []):
            files = [f for f in v.get('video_files', []) if f.get('width')==1080 and f.get('height')==1920]
            files = files or sorted(v.get('video_files', []), key=lambda f:(f.get('width') or 0)*(f.get('height') or 0), reverse=True)
            if not files: continue
            b = files[0]
            out.append((v['id'], v.get('duration'), b['link'], v['url']))
        return out

    terms = ['open old bible dark candle','jesus cross light rays','ancient parchment scroll','sunrise clouds god rays','sheep shepherd field morning','white dove flying sky','olive grove sunlight','sea of galilee boat','cathedral light through window','burning candle flame dark']
    for t in terms:
        try:
            res = search(t)
            print('== %s (%d):' % (t, len(res)))
            for r in res[:4]:
                print('   id=%s dur=%ss %s' % (r[0], r[1], r[3]))
        except Exception as e:
            print('[%s] err %s' % (t, e))
        time.sleep(0.4)