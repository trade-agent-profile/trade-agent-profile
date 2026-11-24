"""古い版の shipment.json を、いまの版（共通データ契約 0.1.1）の形に書き換える。

もとのファイルは変えない。書き換えた写しを、--out で指定したフォルダに書き出す
（同じ名前のファイルがすでにあれば、上書きしない）。値は変えず、足された項目を
「まだ分からない」（null。通知先は空の一覧）で足すだけ。

古い版のデータは、書き換えなくても検証に合格する。書き換えるのは、足された項目を
使いたいときだけでよい。

使い方（PowerShell）:
    uv run python scripts\\upgrade.py samples\\v0.1.0\\valid --out upgraded
    uv run python scripts\\upgrade.py 自分のファイル.json --out 書き出し先のフォルダ --lang ja
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trade_agent_profile.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["upgrade", *sys.argv[1:]]))
