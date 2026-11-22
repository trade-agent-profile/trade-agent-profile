"""見本の2つのエージェント（相手側と荷主側）を、A2A のエージェントとして組み立てる。

どちらも台本と規則だけで動き、AI は使わない。待ち受けは、このパソコンの中だけで行う。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from a2a.types import AgentCard
from starlette.applications import Starlette

from .a2a_agent import build_agent_card, build_app, decline_everything
from .agents import BrokerAgent
from .inbox import InboxStore, Receiver

_JST = timezone(timedelta(hours=9))
BROKER_ACCEPTS = [
    "quote_request",
    "booking_request",
    "document_submission",
    "approval",
    "rejection",
]
SHIPPER_NAME = "Demo Resource Recovery Co., Ltd."


def now_text() -> str:
    """いまの日時（日本時間、時差つき）。"""
    return datetime.now(_JST).isoformat(timespec="seconds")


def new_uuid() -> str:
    return str(uuid.uuid4())


def quiet_logs() -> None:
    """通信の部品が出す、利用者には要らない記録を減らす。"""
    for name in ("a2a", "uvicorn", "httpx"):
        logging.getLogger(name).setLevel(logging.ERROR)


def broker_receiver(
    clock: Callable[[], str] = now_text,
    new_id: Callable[[], str] = new_uuid,
    store: InboxStore | None = None,
) -> Receiver:
    """相手側（フォワーダー兼通関業者）の受付。"""
    broker = BrokerAgent()
    return Receiver(
        broker, sender=broker.sender, store=store or InboxStore(), clock=clock, new_id=new_id
    )


def broker_card(url: str) -> AgentCard:
    return build_agent_card(
        name=BrokerAgent.NAME,
        description=(
            "Reference forwarder and customs broker agent of the experimental "
            "trade-agent-profile. Scripted and rule-based; no AI. All data is fictional."
        ),
        url=url,
        roles=["forwarder", "customs_broker"],
        accepts=BROKER_ACCEPTS,
    )


def broker_app(port: int, receiver: Receiver | None = None) -> tuple[Starlette, AgentCard]:
    """相手側のエージェントのアプリと AgentCard。"""
    card = broker_card(f"http://127.0.0.1:{port}/")
    return build_app(receiver or broker_receiver(), card), card


def shipper_app(port: int) -> tuple[Starlette, AgentCard]:
    """荷主側のエージェントのアプリと AgentCard。

    荷主側は送る役なので、受付は何も引き受けない（届いたメッセージは断る）。
    """
    sender = {"role": "shipper", "name": SHIPPER_NAME, "id": "demo-shipper"}
    receiver = Receiver(
        decline_everything, sender=sender, store=InboxStore(), clock=now_text, new_id=new_uuid
    )
    card = build_agent_card(
        name=SHIPPER_NAME,
        description=(
            "Reference shipper agent of the experimental trade-agent-profile. It sends "
            "messages and accepts none. Scripted; no AI. All data is fictional."
        ),
        url=f"http://127.0.0.1:{port}/",
        roles=["shipper"],
        accepts=[],
    )
    return build_app(receiver, card), card
