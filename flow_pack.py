"""Flow 반자동 워크플로우: scenes JSON -> Google Flow 복붙 프롬프트 팩 생성.

형이 Google Flow(웹 UI)에서 배경 영상을 수동 생성할 수 있도록 장면별 프롬프트를
묶어 flow_packs/<base>/ 폴더에 만든다.

생성물:
  prompts.txt    복붙용 프롬프트 (영어, 한 줄 한 장면) + 한국어 내레이션 참조
  flow_map.json  장면 인덱스 -> 클립 파일명 매핑 (flow_import.py가 사용)
  README.md      따라 할 순서 안내

저장 규칙: Flow에서 생성한 클립은 bg/flow/<base>/scene_01.mp4 ... 로 저장한다.
scene_00.mp4는 훅(hook) 전용(있으면 좋음, 없으면 기존 이미지 유지).

사용법:
  python flow_pack.py scripts/<base>-scenes.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PACK_DIR = ROOT / "flow_packs"
FLOW_DIR = ROOT / "bg" / "flow"

# Flow(Veo)는 영어 프롬프트가 가장 잘 먹힌다. scene_plan.py가 붙인
# camera/mood 값을 실제 영문 연출 문구로 확장한다.
CAMERA_EN = {
    "slow_push": "slow push-in toward the subject",
    "tilt_up": "slow tilt upward",
    "rise": "camera rises slowly",
    "zoom_out": "slow zoom out",
    "pan_left": "slow pan to the left",
    "pan_right": "slow pan to the right",
    "none": "static locked-off camera",
    "auto": "slow cinematic camera movement",
}

MOOD_LIGHT = {
    "reverent": "warm divine golden light with volumetric rays",
    "scholarly": "warm candlelight, intimate and focused",
    "tense": "low-key dramatic lighting with deep shadows",
    "majestic": "epic god rays breaking through clouds, awe-inspiring",
    "triumphant": "bright radiant light, uplifting and hopeful",
    "contemplative": "soft ambient light, peaceful and quiet",
}

# 모든 장면에 공통으로 붙는 스타일 앵커. Flow에서 여러 클립을 한 번에 생성하면
# 같은 스타일이 유지되므로 세트로 만들수록 일관성이 좋다.
STYLE_ANCHOR = (
    "Vertical 9:16 cinematic video, 8 seconds, photorealistic, "
    "subtle film grain, no text, no captions, no people, no watermarks."
)


def flow_prompt(scene: dict, index: int) -> str:
    """장면 하나를 Flow용 영문 프롬프트 한 줄로 만든다."""
    visual = (scene.get("visual_prompt") or "").strip().rstrip(".")
    camera = CAMERA_EN.get(scene.get("camera", "auto"), CAMERA_EN["auto"])
    mood = scene.get("mood", "")
    light = MOOD_LIGHT.get(mood, MOOD_LIGHT["contemplative"])
    parts = [p for p in (visual + ".", f"Camera: {camera}.", f"Lighting: {light}.") if p]
    return " ".join(parts) + " " + STYLE_ANCHOR


def build_pack(data: dict, base: str) -> dict:
    """scenes JSON -> 팩 딕셔너리(프롬프트 줄 + 매핑)."""
    pack_dir = PACK_DIR / base
    save_dir = FLOW_DIR / base
    clips: list[dict] = []

    # 훅 (scene_00, 선택). hook_bg가 이미지면 Flow 클립으로 대체 가능.
    if data.get("hook"):
        clips.append({
            "index": 0,
            "file": "scene_00.mp4",
            "role": "hook",
            "narration": data.get("hook_voice") or data.get("hook", ""),
            "prompt": flow_prompt({
                "visual_prompt": (
                    "dramatic cinematic background for a bold Bible verse hook, "
                    "ancient scroll and radiant light"
                ),
                "camera": "slow_push",
                "mood": "majestic",
            }, 0),
        })

    # 본문 장면들
    blocks = data.get("verses") or [data]
    idx = 1
    for block in blocks:
        for scene in block.get("scenes") or []:
            clips.append({
                "index": idx,
                "file": f"scene_{idx:02d}.mp4",
                "role": "scene",
                "narration": scene.get("narration", ""),
                "prompt": flow_prompt(scene, idx),
            })
            idx += 1

    return {
        "base": base,
        "save_dir": str(save_dir).replace("\\", "/"),
        "clip_count": len(clips),
        "clips": clips,
    }


def write_pack(pack: dict) -> None:
    base = pack["base"]
    pack_dir = PACK_DIR / base
    pack_dir.mkdir(parents=True, exist_ok=True)

    # prompts.txt: 복붙 1순위 파일. 한 줄 = 한 장면.
    lines = [
        f"# {base} — Flow 복붙 프롬프트 ({pack['clip_count']}개)",
        "# Flow(https://flow.google.com)에 한 줄씩 붙여넣고 9:16, 8초로 생성하세요.",
        "# 생성한 클립은 그냥 C:\\Users\\uieta\\Downloads\\googleflow 폴더에 저장하면",
        "# (이름 자동 매칭됨) 내가 bg/flow/<base>/로 옮기고 렌더까지 이어간다.",
        "",
    ]
    for clip in pack["clips"]:
        lines.append(f"### {clip['file']} — {clip['role']}")
        lines.append(clip["prompt"])
        lines.append("")
    (pack_dir / "prompts.txt").write_text("\n".join(lines), encoding="utf-8")

    # flow_map.json: flow_import.py가 읽는 매핑
    (pack_dir / "flow_map.json").write_text(
        json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # README.md: 형용 절차 안내
    readme = f"""# Flow 반자동 워크플로우 — {base}

## 절차 (5분)

1. **Flow 열기**: https://flow.google.com (Google 계정 로그인)
2. **프롬프트 복붙**: `prompts.txt`를 열고 `### scene_XX.mp4` 아래 한 줄을
   Flow 입력창에 붙여넣기 → **9:16 (세로), 8초** 설정 → 생성.
3. **클립 저장**: 마음에 드는 결과를 다운로드해서
   `C:\\Users\\uieta\\Downloads\\googleflow` 폴더에 저장.
   - 파일명은 아무거나 OK (예: Ancient_scroll_with_radiant_light_202608241444.mp4)
   - 내가 프롬프트 키워드로 자동 매칭해서 `bg/flow/{base}/scene_XX.mp4`로 옮긴다.
   - 훅용 `scene_00`은 선택 (없으면 기존 AI 이미지 유지).
   - 장면마다 꼭 채울 필요 없음 — 없는 장면은 기존 Pexels 클립으로 자동 대체.
4. **내게 알림**: "Flow 클립 넣었어"라고 말하면 내가 감지 → 자막·TTS·합성·QA
   까지 자동으로 이어간다.

## 팁

- 한 Flow 세션에서 여러 클립을 연속 생성하면 스타일 일관성이 좋다.
- `### scene_XX.mp4` 아래 **한 줄만** 복사하세요 (두 번째 줄부터는 한국어
  내레이션 참조라 Flow에 붙여넣으면 안 됨).
- 생성 결과에 글자/사람 얼굴이 나오면 재생성 (프롬프트에 no text 포함됨).
- Flow 무료 티어는 720p(720x1280) — 1080p로 업스케일되지만 PRO면 1080p 옵션
  확인해 볼 것.

## 장면 목록

| 클립 | 역할 | 내레이션 (한국어 참조) |
|---|---|---|
"""
    for clip in pack["clips"]:
        narr = (clip["narration"] or "").replace("\n", " ")[:60]
        readme += f"| `{clip['file']}` | {clip['role']} | {narr} |\n"
    (pack_dir / "README.md").write_text(readme, encoding="utf-8")

    print(f"flow pack: {pack['clip_count']} clips -> {pack_dir}")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python flow_pack.py scripts/<base>-scenes.json")
    src = Path(sys.argv[1])
    data = json.loads(src.read_text(encoding="utf-8"))
    base = src.stem
    pack = build_pack(data, base)
    write_pack(pack)


if __name__ == "__main__":
    main()
