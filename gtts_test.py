import json, urllib.request, urllib.parse, sys
from pathlib import Path

def read_key(env_path, prefix):
    for line in Path(env_path).read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if s.startswith(prefix):
            return s.split('=', 1)[1].strip().strip('"').strip("'")
    return None

key = read_key(Path.home()/'.hermes'/'.env', 'GOOGLE_API_KEY')
if not key:
    sys.exit('no google key')

# 1) 사용 가능한 한국어 목소리 조회
url = 'https://texttospeech.googleapis.com/v1/voices?languageCode=ko-KR&key=%s' % urllib.parse.quote(key)
req = urllib.request.Request(url)
try:
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.loads(r.read().decode())
    print('=== ko-KR 사용 가능 목소리 ===')
    for v in d.get('voices', []):
        g = ','.join(v.get('ssmlGender') or [])
        print('%s (%s)' % (v['name'], g))
except urllib.error.HTTPError as e:
    print('HTTP', e.code, e.read().decode()[:500])
except Exception as e:
    print('ERR', e)