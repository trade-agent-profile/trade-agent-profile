"""検証コマンドの入口（公開名が変わっても、この呼び方は変わらない）。

使い方（PowerShell）:
    uv run python scripts\\validate.py samples\\valid
    uv run python scripts\\validate.py samples\\valid\\*.json
    uv run python scripts\\validate.py ファイル1.json ファイル2.json --lang ja
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trade_agent_profile.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["validate", *sys.argv[1:]]))
