"""ほかのプロジェクトへ渡す配布物（dist/contract-v0.1/）をそろえる。

正本（schema/ と samples/）から写すだけ。README.ja.md と CHANGELOG.md は配布物の
フォルダに直接置いてあり、ここでは書き換えない。

使い方（PowerShell）:
    uv run python scripts\\build_dist.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "contract-v0.1"
AUTHORED = ("README.ja.md", "CHANGELOG.md")


def planned() -> dict[Path, Path]:
    """写すファイルの一覧（写し先 → 正本）。"""
    files = {DIST / "shipment.schema.json": ROOT / "schema" / "shipment.schema.json"}
    samples = ROOT / "samples"
    for folder in ("valid", "invalid"):  # 契約（shipment.json）の見本だけを配る
        for source in sorted((samples / folder).glob("*.json")):
            files[DIST / "samples" / source.relative_to(samples)] = source
    return files


def stale() -> list[Path]:
    """正本にはもうないのに、配布物に残っているファイル。"""
    files = planned()
    return sorted(path for path in (DIST / "samples").rglob("*.json") if path not in files)


def main() -> int:
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    files = planned()
    for target, source in files.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    problems = 0
    for path in stale():  # 勝手には消さず、知らせるだけにする
        print(f"正本にないファイルが残っています: {path.relative_to(ROOT).as_posix()}")
        problems += 1
    for name in AUTHORED:
        if not (DIST / name).is_file():
            print(f"配布物に {name} がありません")
            problems += 1
    print(f"配布物をそろえました: {len(files)} ファイル → dist/contract-v0.1/")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
