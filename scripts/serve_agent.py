"""見本の相手側エージェント（フォワーダー兼通関業者）を、A2A のエージェントとして待ち受けさせる。

待ち受けは、このパソコンの中だけ（127.0.0.1）で行う。外には開かない。
止めるときは、この窓で Ctrl+C を押す。

使い方（PowerShell）:
    uv run python scripts\\serve_agent.py
    uv run python scripts\\serve_agent.py --port 8027
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trade_agent_profile import i18n  # noqa: E402
from trade_agent_profile.cli import setup_stdio  # noqa: E402
from trade_agent_profile.reference import broker_app  # noqa: E402

DEFAULT_PORT = 8027


def main() -> int:
    setup_stdio()
    parser = argparse.ArgumentParser(description="見本の相手側エージェント / Reference agent")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    app, card = broker_app(args.port)
    url = f"http://127.0.0.1:{args.port}"
    print(i18n.catalog("ja")["ui"]["notice"])
    print(f"見本の相手側エージェント「{card.name}」が待ち受けています: {url}")
    print(f"AgentCard: {url}/.well-known/agent-card.json")
    print("止めるときは Ctrl+C を押してください。")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
