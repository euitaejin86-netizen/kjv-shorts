import asyncio, subprocess
from pathlib import Path
import edge_tts

OUT = Path(r"C:\Users\uieta\KEEPBIBLE\kjv-shorts\tts_samples")
OUT.mkdir(exist_ok=True, parents=True)

# 같은 본문으로 여러 목소리/톤 비교
TEXT = "하늘과 땅은 없어지겠으나, 내 말들은 없어지지 아니하리라."
VOICES = [
    ("1_인준기본.mp3",  TEXT, "ko-KR-InJoonNeural",    "+0%", "+0Hz"),   # 현재
    ("2_현수.mp3",      TEXT, "ko-KR-HyunsuMultilingualNeural", "-5%", "+0Hz"), # 다국어, 느리게
    ("3_현수_엄숙.mp3", TEXT, "ko-KR-HyunsuMultilingualNeural", "-10%", "-4Hz"), # 더 무게감
    ("4_인준_엄숙.mp3", TEXT, "ko-KR-InJoonNeural",    "-10%", "-3Hz"),  # 설교 느낌
]

async def gen():
    for fname, text, voice, rate, pitch in VOICES:
        c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        p = OUT / fname
        await c.save(str(p))
        print("생성", fname, p.stat().st_size//1024, "KB")

asyncio.run(gen())
print("완료")