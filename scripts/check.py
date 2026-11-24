"""完了報告の前に必ず実行する総合チェック。

Ruff → pytest → 見本の検証 → 公開前の検査（1段目） → 適合テスト の順に実行し、最後の行に CHECK OK か CHECK NG を出す。

使い方（PowerShell）:
    uv run python scripts\\check.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

STEPS = [
    ("Ruff", [PYTHON, "-m", "ruff", "check", "."]),
    ("pytest", [PYTHON, "-m", "pytest", "-q"]),
    (
        "見本の検証（正しい例）",
        [PYTHON, "scripts/validate.py", "samples/valid", "--quiet", "--lang", "ja"],
    ),
    (
        "見本の検証（誤り例）",
        [PYTHON, "scripts/validate.py", "samples/invalid", "--expected", "--quiet", "--lang", "ja"],
    ),
    (
        "見本の検証（前の版 0.1.0 の正しい例。書き換えなくても合格すること）",
        [PYTHON, "scripts/validate.py", "samples/v0.1.0/valid", "--quiet", "--lang", "ja"],
    ),
    (
        "見本の検証（前の版 0.1.0 の誤り例）",
        [
            PYTHON,
            "scripts/validate.py",
            "samples/v0.1.0/invalid",
            "--expected",
            "--quiet",
            "--lang",
            "ja",
        ],
    ),
    (
        "見本の検証（メッセージ）",
        [PYTHON, "scripts/validate.py", "samples/messages", "--quiet", "--lang", "ja"],
    ),
    (
        "公開前の検査（1段目。名前の一覧を使う2段目は、依頼者が自分で実行する）",
        [PYTHON, "scripts/prepublish_check.py", "--no-report", "--quiet", "--lang", "ja"],
    ),
    (
        "適合テスト（見本の実装を、このパソコンの中で起動して試す）",
        [PYTHON, "scripts/conformance.py", "--self-test", "--quiet", "--lang", "ja"],
    ),
]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if not stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="replace")
    env = dict(os.environ, PYTHONUTF8="1")
    failed: list[str] = []
    for name, command in STEPS:
        print(f"--- {name}", flush=True)
        done = subprocess.run(command, cwd=ROOT, env=env, check=False)
        if done.returncode != 0:
            failed.append(name)
    if failed:
        print("失敗した段: " + "、".join(failed))
        print("CHECK NG")
        return 1
    print("CHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
