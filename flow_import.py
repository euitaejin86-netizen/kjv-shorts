"""Flow에서 생성한 클립을 scenes JSON에 반영한다.

인박스(기본 C:\\Users\\uieta\\Downloads\\googleflow)에 저장된 Flow 클립을
bg/flow/<base>/scene_NN.mp4로 옮기고, 각 scene의 media를 해당 클립으로 교체한
scripts/<base>-flow.json을 만든다. 없는 장면은 기존 로컬 미디어를 그대로 쓴다.

파일→장면 매핑 (우선순위):
  1) 파일명에 scene_NN 이 있으면 그 인덱스로.
  2) 아니면 파일명과 flow_map 프롬프트의 단어 겹침 점수로 최적 매칭
     (Flow 파일명이 프롬프트 기반이라 키워드가 그대로 들어간다).
  3) 매칭 실패 시 수정 시각(오래된 순)으로 남은 장면에 순서대로 할당.

사용법:
  python flow_import.py scripts/<base>-scenes.json [--inbox <폴더>]
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
FLOW_DIR = ROOT / "bg" / "flow"
DEFAULT_INBOX = Path.home() / "Downloads" / "googleflow"

VIDEO_EXT = (".mp4", ".webm", ".mov")
_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    """영문 소문자 토큰 집합 (3자 이상만 — 관사/전치사 노이즈 제거)."""
    return {t for t in _WORD_RE.findall(text.lower()) if len(t) >= 3}


def match_clip(filename: str, clips: list[dict]) -> tuple[int | None, int]:
    """파일명을 클립에 매칭한다. (인덱스, 점수) — 0점이면 매칭 실패."""
    name = _tokens(filename)

    # 1) 파일명에 scene_NN 직접 표기
    m = re.search(r"scene_(\d+)", filename.lower())
    if m:
        idx = int(m.group(1))
        if 0 <= idx < len(clips):
            return idx, 999

    # 2) 프롬프트 단어 겹침
    best_idx, best_score = None, 0
    for i, clip in enumerate(clips):
        prompt_tokens = _tokens(clip["prompt"]) | _tokens(clip.get("role", ""))
        overlap = len(name & prompt_tokens)
        if overlap > best_score:
            best_idx, best_score = i, overlap
    return best_idx, best_score


def import_from_inbox(data: dict, base: str, inbox: Path) -> tuple[list[str], list[str]]:
    """인박스 파일을 bg/flow/<base>/로 옮기고 (옮긴 목록, 실패 목록) 반환."""
    from flow_pack import build_pack  # flow_map.json 재생성 없이 프롬프트 재사용

    pack = build_pack(data, base)
    clips = pack["clips"]
    save_dir = FLOW_DIR / base
    save_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        [p for p in inbox.iterdir() if p.suffix.lower() in VIDEO_EXT],
        key=lambda p: p.stat().st_mtime,
    )
    moved: list[str] = []
    failed: list[str] = []
    used_idx: set[int] = set()

    for f in files:
        idx, score = match_clip(f.stem, clips)
        if idx is None or (score == 0 and len(files) > len(clips)):
            failed.append(f"{f.name} (매칭 불가 — 남는 파일)")
            continue
        if score == 0:
            # 겹침 0 = 순서 할당 (오래된 순). 아직 안 쓴 첫 인덱스로.
            idx = next((i for i in range(len(clips)) if i not in used_idx), None)
            if idx is None:
                failed.append(f"{f.name} (장면 초과)")
                continue
        if idx in used_idx:
            print(f"  [경고] {f.name} -> scene_{idx:02d} 이미 있음. 새 파일로 교체")
        used_idx.add(idx)
        target = save_dir / clips[idx]["file"]
        shutil.move(str(f), str(target))
        moved.append(f"{f.name} -> {clips[idx]['file']} ({clips[idx]['role']})")

    return moved, failed


def apply_if_exists(base: str, data: dict) -> tuple[list[str], list[str]]:
    """bg/flow/<base>/에 있는 클립을 scenes 데이터에 반영한다."""
    out = json.loads(json.dumps(data, ensure_ascii=False))
    save_dir = FLOW_DIR / base
    replaced: list[str] = []
    missing: list[str] = []

    def apply(index: int, target_key: str, target: dict) -> None:
        clip = save_dir / f"scene_{index:02d}.mp4"
        if clip.exists() and clip.suffix.lower() in VIDEO_EXT:
            rel = str(clip.relative_to(ROOT)).replace("\\", "/")
            if target.get(target_key) != rel:
                target[target_key] = rel
                replaced.append(f"scene_{index:02d}.mp4 -> {target_key}")
        else:
            missing.append(f"scene_{index:02d}.mp4")

    if out.get("hook"):
        apply(0, "hook_bg", out)

    blocks = out.get("verses")
    if blocks is None:
        blocks = [out]
    idx = 1
    for block in blocks:
        for scene in block.get("scenes") or []:
            apply(idx, "media", scene)
            idx += 1

    return out, replaced, missing


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python flow_import.py scripts/<base>-scenes.json [--inbox <폴더>]")
    src = Path(sys.argv[1])
    inbox = DEFAULT_INBOX
    if "--inbox" in sys.argv:
        inbox = Path(sys.argv[sys.argv.index("--inbox") + 1])

    data = json.loads(src.read_text(encoding="utf-8"))
    base = src.stem

    if inbox.exists():
        moved, failed = import_from_inbox(data, base, inbox)
        if moved:
            print(f"flow inbox: {len(moved)}개 옮김")
            for m in moved:
                print(f"  [IN] {m}")
        if failed:
            print(f"flow inbox: {len(failed)}개 처리 못함")
            for f in failed:
                print(f"  [!!] {f}")
    else:
        print(f"[--] 인박스 없음: {inbox}")

    out, replaced, missing = apply_if_exists(base, data)
    dst = src.with_name(src.stem.replace("-scenes", "-flow") + ".json")
    # 기존 -flow.json의 인라인 style(예: Flow 클립 훅 상단배치 커스텀)은
    # scenes json에 없으므로 재생성 시 유실된다. 이미 있으면 보존한다.
    if dst.exists():
        try:
            old_style = json.loads(dst.read_text(encoding="utf-8")).get("style")
            if old_style:
                out["style"] = old_style
        except Exception:
            pass
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"flow import: {len(replaced)} clips 적용 -> {dst.name}")
    for r in replaced:
        print(f"  [OK] {r}")
    for m in missing:
        print(f"  [--] {m} (기존 배경 유지)")

    if replaced:
        print(f"\n렌더: python build.py {dst.name}")


if __name__ == "__main__":
    main()
