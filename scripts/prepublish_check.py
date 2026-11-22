"""公開前の検査の入口。秘密情報・実データ・個人の情報が、公開するものに入っていないかを調べる。

1段目（名前の一覧がなくても分かるもの。記録は reports\\prepublish.md）:
    uv run python scripts\\prepublish_check.py
2段目（名前の一覧と作者名。一覧を用意した人が、自分で実行する）:
    uv run python scripts\\prepublish_check.py --names data\\private\\names.txt --author p27-maintainer

終了コード：0＝見つかったものなし、1＝見つかったものあり、2＝実行できない（git の管理下でない など）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trade_agent_profile.prepublish import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--root", str(ROOT), *sys.argv[1:]]))
