"""台本デモを実行し、記録を reports/demo.html に書き出す。

荷主側と相手側（フォワーダー兼通関業者）が、見積依頼から承認までをやり取りする。
AI は使わない。何度実行しても同じ記録になる。

使い方（PowerShell）:
    uv run python scripts\\demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trade_agent_profile.cli import setup_stdio  # noqa: E402
from trade_agent_profile.demo import MAIN_SCENES, run_demo  # noqa: E402
from trade_agent_profile.profile import COMPLETED  # noqa: E402
from trade_agent_profile.report import render  # noqa: E402

TARGET = ROOT / "reports" / "demo.html"


def main() -> int:
    setup_stdio()
    run = run_demo()
    entries = run.entries
    approval = [e for e in entries if e.scene == "approval" and e.sender == "broker"]
    if not approval or approval[-1].state != COMPLETED:
        print("台本デモが承認まで進みませんでした。")
        return 1

    TARGET.parent.mkdir(exist_ok=True)
    TARGET.write_text(render(entries), encoding="utf-8", newline="\n")

    messages = [e for e in entries if e.envelope is not None and not e.duplicate]
    main_messages = [e for e in messages if e.scene in MAIN_SCENES]
    kinds = {e.envelope["message_type"] for e in messages}
    print("台本デモが、見積依頼から承認まで最後まで走りました。")
    print(
        f"やり取りしたメッセージ: {len(messages)}件（本編 {len(main_messages)}件）、種類は {len(kinds)}種類"
    )
    print(f"相手側が実際に処理した回数: {run.broker.calls}回（再送は処理していません）")
    print(f"記録: {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
