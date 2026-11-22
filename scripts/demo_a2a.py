"""台本デモを、2つのエージェントの A2A の通信で実行する。

相手側（フォワーダー兼通関業者）と荷主側の2つを、このパソコンの中だけで待ち受けさせ、
見積依頼から承認までを実際に通信でやり取りする。AI は使わない。
記録は reports/demo-a2a.html に書き出す。

使い方（PowerShell）:
    uv run python scripts\\demo_a2a.py
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trade_agent_profile.a2a_agent import A2ALink, card_summary, fetch_card, free_port, serve  # noqa: E402
from trade_agent_profile.cli import setup_stdio  # noqa: E402
from trade_agent_profile.demo import MAIN_SCENES, run_demo  # noqa: E402
from trade_agent_profile.inbox import Receiver  # noqa: E402
from trade_agent_profile.profile import COMPLETED  # noqa: E402
from trade_agent_profile.reference import broker_app, quiet_logs, shipper_app  # noqa: E402
from trade_agent_profile.report import render  # noqa: E402

TARGET = ROOT / "reports" / "demo-a2a.html"


def main() -> int:
    setup_stdio()
    quiet_logs()
    cards = []
    with ExitStack() as stack:
        shipper_port = free_port()
        app, _ = shipper_app(shipper_port)
        shipper_url = stack.enter_context(serve(app, shipper_port))
        shipper_card = asyncio.run(fetch_card(shipper_url))

        def connect(receiver: Receiver) -> A2ALink:
            """相手側の受付を A2A のエージェントとして待ち受けさせ、そこへ送る口を返す。"""
            port = free_port()
            app, _ = broker_app(port, receiver)
            url = stack.enter_context(serve(app, port))
            card = asyncio.run(fetch_card(url))
            cards.append(card_summary(card))
            return A2ALink(card)

        run = run_demo(connect=connect)
        cards.insert(0, card_summary(shipper_card))

    entries = run.entries
    approval = [e for e in entries if e.scene == "approval" and e.sender == "broker"]
    if not approval or approval[-1].state != COMPLETED:
        print("台本デモが承認まで進みませんでした。")
        return 1

    TARGET.parent.mkdir(exist_ok=True)
    TARGET.write_text(render(entries, wire="a2a", cards=cards), encoding="utf-8", newline="\n")

    messages = [e for e in entries if e.envelope is not None and not e.duplicate]
    main_messages = [e for e in messages if e.scene in MAIN_SCENES]
    kinds = {e.envelope["message_type"] for e in messages}
    print("2つのエージェントが、A2A の通信で、見積依頼から承認まで最後までやり取りしました。")
    print(
        f"やり取りしたメッセージ: {len(messages)}件（本編 {len(main_messages)}件）、種類は {len(kinds)}種類"
    )
    print(f"相手側が実際に処理した回数: {run.broker.calls}回（再送は処理していません）")
    for card in cards:
        declared = "あり" if card["declares_profile"] else "なし"
        print(f"AgentCard: {card['name']}（プロファイルの拡張の宣言: {declared}）")
    print(f"記録: {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
