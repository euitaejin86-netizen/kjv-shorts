"""기존 narration 대본을 3~6초 단위 scenes 타임라인으로 승격한다.

미디어는 교리 내용을 생성하지 않고, 문장 의미 키워드에 따라 검증된 로컬 세로 영상
라이브러리만 선택한다. 생성된 scenes는 사람이 읽을 수 있는 visual_prompt/camera/mood
메타데이터도 포함해 향후 Veo/API 연결 시 그대로 입력으로 쓸 수 있다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent

MEDIA_RULES = [
    (("아버지", "아들", "그리스도", "예수", "하나님"), "bg/video/sunrays_window.mp4", "divine golden light entering a dark sanctuary", "slow_push", "reverent"),
    (("성경", "구절", "번역", "말씀", "본문"), "bg/video/bible_open.mp4", "open King James Bible under warm cinematic light", "slow_push", "scholarly"),
    (("직접", "부르", "말씀하시", "선포"), "bg/video/sun_clouds.mp4", "powerful rays breaking through clouds as a declaration", "tilt_up", "majestic"),
    (("흐리", "무디어", "차이", "사소"), "bg/video/candle_dark.mp4", "single flame nearly obscured by darkness", "slow_push", "tense"),
    (("왕좌", "왕국", "영원"), "bg/video/clouds_light.mp4", "eternal kingdom suggested by luminous clouds", "rise", "triumphant"),
]
DEFAULT_MEDIA = ("bg/video/candle_serene.mp4", "quiet candle beside scripture", "slow_push", "contemplative")


def split_for_scenes(text: str, target_chars: int = 34) -> list[str]:
    """문장 의미를 유지하며 쉼표/연결어 경계에서 약 18~48자로 분할한다."""
    text = text.strip()
    if len(text) <= 48:
        return [text]
    # 종결기호 또는 쉼표 뒤를 우선 경계로 사용한다.
    atoms = [x.strip() for x in re.split(r"(?<=[.!?])\s+|(?<=,)\s+", text) if x.strip()]
    if len(atoms) == 1:
        atoms = [x.strip() for x in re.split(r"(?=(?:그런데|곧|마치|이것이|흠정역에서는|성경이))", text) if x.strip()]
    out, cur = [], ""
    for atom in atoms:
        candidate = f"{cur} {atom}".strip()
        if cur and len(candidate) > 48:
            out.append(cur)
            cur = atom
        else:
            cur = candidate
        if len(cur) >= target_chars and cur.endswith((".", "?", "!", ",")):
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    # 지나치게 짧은 꼬리는 앞 장면에 합친다.
    if len(out) > 1 and len(out[-1]) < 14:
        out[-2] = f"{out[-2]} {out.pop()}"
    return out


def visual_for(text: str, index: int) -> dict:
    # 첫 키워드 하나만 맞았다고 장면을 고르면 '아들'이 들어간 거의 모든 문장이
    # 같은 빛 장면이 된다. 일치 키워드 수가 가장 많은 의미군을 선택한다.
    scored = []
    for priority, (keys, media, prompt, camera, mood) in enumerate(MEDIA_RULES):
        score = sum(1 for k in keys if k in text)
        if score:
            scored.append((score, -priority, media, prompt, camera, mood))
    if scored:
        _score, _priority, media, prompt, camera, mood = max(scored)
    else:
        media, prompt, camera, mood = DEFAULT_MEDIA
    return {"media": media, "visual_prompt": prompt, "camera": camera, "mood": mood}


def upgrade(data: dict) -> dict:
    out = json.loads(json.dumps(data, ensure_ascii=False))
    blocks = out.get("verses") or [out]
    for block in blocks:
        narr = block.get("narration") or []
        scenes = []
        idx = 0
        for sentence in narr:
            for chunk in split_for_scenes(sentence):
                visual = visual_for(chunk, idx)
                scenes.append({
                    "narration": chunk,
                    "highlight": block.get("highlight", out.get("highlight", [])),
                    **visual,
                    "motion": "auto",
                })
                idx += 1
        block["scenes"] = scenes
    out["scene_plan_version"] = 1
    return out


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python scene_plan.py scripts/input.json [scripts/output.json]")
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name(src.stem + "-scenes.json")
    data = upgrade(json.loads(src.read_text(encoding="utf-8")))
    dst.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    count = sum(len(b.get("scenes", [])) for b in (data.get("verses") or [data]))
    print(f"scene plan: {count} scenes -> {dst}")


if __name__ == "__main__":
    main()
