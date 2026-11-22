"""台本デモ：荷主側と相手側（フォワーダー兼通関業者）が、見積依頼から承認までをやり取りする。

AI は使わない。日時と識別子は決まった値にしてあり、何度実行しても同じ記録になる。
何も指定しなければ通信はせず、1つのプログラムの中で受け渡す。
同じ台本を A2A の通信で実行するときは、connect に送り先のつなぎ方を渡す（scripts/demo_a2a.py）。
"""

from __future__ import annotations

import copy
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .agents import BrokerAgent
from .inbox import InboxStore, Outcome, Receiver
from .messages import new_message

MAIN_SCENES = ("quote", "booking", "documents", "resubmission", "approval")
EXTRA_SCENES = ("resend", "version", "decline")

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://example.invalid/trade-agent-profile/demo")
_DATA = Path(__file__).parent / "data" / "demo_shipment.json"
_WRONG_GROSS_WEIGHT = "21480.000"  # 正本は 21840.000。2つの数字を入れ違えた誤り


class ScriptClock:
    """台本用の時計。呼ぶたびに2分進む。"""

    def __init__(self, start: str) -> None:
        self._now = datetime.fromisoformat(start)

    def set(self, text: str) -> None:
        self._now = datetime.fromisoformat(text)

    def __call__(self) -> str:
        text = self._now.isoformat(timespec="seconds")
        self._now += timedelta(minutes=2)
        return text


class ScriptIds:
    """台本用の識別子。呼ぶたびに、決まった順番の UUID を返す。"""

    def __init__(self) -> None:
        self._count = 0

    def __call__(self) -> str:
        self._count += 1
        return str(uuid.uuid5(_NAMESPACE, str(self._count)))


@dataclass
class Entry:
    """記録の1行。"""

    scene: str
    at: str
    sender: str  # "shipper" か "broker"
    kind: (
        str  # message（依頼側が送る）/ artifact（結果）/ status（状態に添える）/ state（状態だけ）
    )
    envelope: dict[str, Any] | None
    task_id: str | None = None
    state: str | None = None
    duplicate: bool = False


def load_demo_shipment() -> dict[str, Any]:
    """台本デモで使う架空の船積み（書類の値は正本とそろっている）。"""
    with _DATA.open(encoding="utf-8") as handle:
        return json.load(handle)


class DemoRun:
    """1回の台本デモ。荷主側の送信と、相手側の受け付けをつなぐ。"""

    def __init__(
        self, shipment: dict[str, Any], connect: Callable[[Receiver], Any] | None = None
    ) -> None:
        self.clock = ScriptClock("2026-12-01T09:00:00+09:00")
        self.ids = ScriptIds()
        self.broker = BrokerAgent()
        self.store = InboxStore()
        self.receiver = Receiver(
            self.broker,
            sender=self.broker.sender,
            store=self.store,
            clock=self.clock,
            new_id=self.ids,
        )
        # 相手側への渡し方。何も指定しなければ、同じプログラムの中で直接渡す。
        # connect を渡すと、受け付けを通信（A2A）の向こうに置いて、そこへ送る
        self.link = connect(self.receiver) if connect is not None else self.receiver
        self.shipper = {
            "role": "shipper",
            "name": shipment["parties"]["shipper"]["name"],
            "id": "demo-shipper",
        }
        self.entries: list[Entry] = []

    def send(
        self,
        scene: str,
        message_type: str,
        payload: dict[str, Any],
        *,
        thread: str,
        in_reply_to: str | None = None,
        task_id: str | None = None,
        profile_version: str | None = None,
    ) -> tuple[Outcome, dict[str, Any]]:
        """荷主側が新しいメッセージを作って送る。"""
        envelope = new_message(
            message_type,
            payload,
            sender=self.shipper,
            correlation_id=thread,
            sent_at=self.clock(),
            message_id=self.ids(),
            in_reply_to=in_reply_to,
        )
        if profile_version is not None:
            envelope["profile_version"] = profile_version
        return self.deliver(scene, envelope, task_id=task_id), envelope

    def deliver(
        self,
        scene: str,
        envelope: dict[str, Any],
        *,
        task_id: str | None = None,
        resend: bool = False,
    ) -> Outcome:
        """封筒を相手側に渡し、やり取りを記録する。"""
        sent_at = self.clock() if resend else envelope["sent_at"]
        self.entries.append(Entry(scene, sent_at, "shipper", "message", envelope, duplicate=resend))
        outcome = self.link.receive(envelope, task_id)
        when = self.clock() if outcome.duplicate else outcome.at
        replies: list[tuple[str, dict[str, Any] | None]] = [
            ("artifact", message) for message in outcome.artifacts
        ]
        if outcome.status_message is not None:
            replies.append(("status", outcome.status_message))
        if not replies:
            replies.append(("state", None))
        for kind, message in replies:
            entry = Entry(
                scene,
                when,
                "broker",
                kind,
                message,
                outcome.task_id,
                outcome.state,
                outcome.duplicate,
            )
            self.entries.append(entry)
        return outcome


def _set_document_value(shipment: dict[str, Any], doc_type: str, key: str, value: Any) -> None:
    for document in shipment["documents"]:
        if document["doc_type"] == doc_type and key in document["fields"]:
            document["fields"][key]["value"] = value
            return
    raise KeyError(f"{doc_type} に {key} がありません")


def run_demo(
    shipment: dict[str, Any] | None = None, connect: Callable[[Receiver], Any] | None = None
) -> DemoRun:
    """台本を最初から最後まで実行する。connect を渡すと、通信（A2A）を通して実行する。"""
    full = copy.deepcopy(shipment) if shipment is not None else load_demo_shipment()
    run = DemoRun(full, connect)
    thread = run.ids()  # 1件の船積みについての会話の識別子
    shipment_id = full["shipment_id"]

    planned = copy.deepcopy(full)  # 見積とブッキングの時点では、書類はまだない
    planned["status"] = "draft"
    planned["documents"] = []
    planned["events"] = planned["events"][:1]

    # 1. 見積
    payload = {"shipment": planned, "reply_by": "2026-12-03", "note": None}
    outcome, _ = run.send("quote", "quote_request", payload, thread=thread)
    quote = outcome.artifacts[0]

    # 2. ブッキング
    run.clock.set("2026-12-01T14:00:00+09:00")
    payload = {
        "shipment": planned,
        "quote_number": quote["payload"]["quote_number"],
        "note": None,
    }
    outcome, booking_request = run.send(
        "booking", "booking_request", payload, thread=thread, in_reply_to=quote["message_id"]
    )

    # 3. 書類の提出（パッキングリストの総重量が正本と違う）→ 食い違いの通知
    run.clock.set("2026-12-07T10:00:00+09:00")
    first = copy.deepcopy(full)
    _set_document_value(first, "packing_list", "totals.gross_weight_kg", _WRONG_GROSS_WEIGHT)
    payload = {"shipment": first, "note": None}
    outcome, _ = run.send("documents", "document_submission", payload, thread=thread)
    notice = outcome.status_message
    assert notice is not None

    # 4. 直した書類で、同じタスクの続きとして出し直す → 申告の下書き
    run.clock.set("2026-12-08T09:30:00+09:00")
    payload = {
        "shipment": full,
        "note": "The packing list was reissued with the correct gross weight.",
    }
    outcome, _ = run.send(
        "resubmission",
        "document_submission",
        payload,
        thread=thread,
        in_reply_to=notice["message_id"],
        task_id=outcome.task_id,
    )
    draft = outcome.artifacts[0]

    # 5. 承認
    run.clock.set("2026-12-08T15:00:00+09:00")
    payload = {"shipment_id": shipment_id, "note": None}
    run.send("approval", "approval", payload, thread=thread, in_reply_to=draft["message_id"])

    # 補足1. 同じメッセージの再送（処理されない）
    run.clock.set("2026-12-09T10:00:00+09:00")
    run.deliver("resend", booking_request, resend=True)

    # 補足2. 版が合わないとき
    run.clock.set("2026-12-09T10:30:00+09:00")
    payload = {"shipment": planned, "reply_by": None, "note": None}
    run.send("version", "quote_request", payload, thread=run.ids(), profile_version="0.2.0")

    # 補足3. 見積を断る（別の会話）
    run.clock.set("2026-12-09T11:00:00+09:00")
    other = run.ids()
    payload = {"shipment": planned, "reply_by": None, "note": None}
    outcome, _ = run.send("decline", "quote_request", payload, thread=other)
    second = outcome.artifacts[0]
    payload = {
        "shipment_id": shipment_id,
        "reason": "The quoted total is above our budget for this shipment.",
        "note": None,
    }
    run.send("decline", "rejection", payload, thread=other, in_reply_to=second["message_id"])
    return run
