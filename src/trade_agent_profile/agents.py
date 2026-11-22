"""台本どおりに動く、相手側の見本。AI は使わず、決まった規則だけで返事を作る。

想定：相手側は1社がフォワーダーと通関業者を兼ねる。見積とブッキングはフォワーダー
の立場で、書類の確認と申告の下書きは通関業者の立場で返事をする。
見積の料金表は架空の見本で、実際の提示ではない。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .declaration import build_declaration_draft
from .inbox import Reply, error_payload
from .issues import Issue
from .profile import COMPLETED, INPUT_REQUIRED, REJECTED
from .rules import find_discrepancies

# 架空の料金表（円）。見本のための数字で、実際の料金ではない
_PER_CONTAINER = (
    ("Ocean freight (sample tariff)", Decimal("85000")),
    ("Terminal handling (sample tariff)", Decimal("32000")),
)
_WITHOUT_CONTAINER = (("Freight (sample tariff)", Decimal("60000")),)
_PER_SHIPMENT = (
    ("Export customs clearance (sample tariff)", Decimal("11800")),
    ("Documentation (sample tariff)", Decimal("5500")),
)
_QUOTE_NOTE = "Mock quote calculated from a fixed sample tariff. It is not a real offer."
_QUOTE_VALID_DAYS = 14
_CUTOFF_DAYS_BEFORE_ETD = 2


class BrokerAgent:
    """相手側（フォワーダー兼通関業者）の処理。"""

    NAME = "Demo Forwarding & Customs K.K."
    AGENT_ID = "demo-forwarder-broker"

    def __init__(self) -> None:
        self.threads: dict[str, dict[str, Any]] = {}  # 会話（correlation_id）ごとの控え
        self.calls = 0  # 実際に処理した回数。二重処理をしていないことの確認に使う
        self._serial = {"Q": 0, "BK": 0, "DD": 0}

    @property
    def sender(self) -> dict[str, str]:
        return {"role": "forwarder", "name": self.NAME, "id": self.AGENT_ID}

    def __call__(self, envelope: dict[str, Any]) -> Reply:
        self.calls += 1
        handler = getattr(self, f"_on_{envelope['message_type']}", None)
        if handler is None:
            return Reply(REJECTED, "error", error_payload("UNEXPECTED_MESSAGE"))
        thread = self.threads.setdefault(envelope["correlation_id"], {})
        return handler(envelope, thread)

    def _next(self, prefix: str) -> str:
        self._serial[prefix] += 1
        return f"{prefix}-{self._serial[prefix]:04d}"

    def _on_quote_request(self, envelope: dict[str, Any], thread: dict[str, Any]) -> Reply:
        shipment = envelope["payload"]["shipment"]
        containers = len(shipment["transport"]["containers"])
        charges = [(name, rate * containers) for name, rate in _PER_CONTAINER]
        if containers == 0:
            charges = list(_WITHOUT_CONTAINER)
        charges += _PER_SHIPMENT
        sent = datetime.fromisoformat(envelope["sent_at"]).date()
        thread["quote_number"] = self._next("Q")
        payload = {
            "shipment_id": shipment["shipment_id"],
            "quote_number": thread["quote_number"],
            "currency": "JPY",
            "charges": [{"name": name, "amount": f"{amount:.2f}"} for name, amount in charges],
            "total": f"{sum(amount for _, amount in charges):.2f}",
            "valid_until": (sent + timedelta(days=_QUOTE_VALID_DAYS)).isoformat(),
            "note": _QUOTE_NOTE,
        }
        return Reply(COMPLETED, "quote", payload, "forwarder")

    def _on_booking_request(self, envelope: dict[str, Any], thread: dict[str, Any]) -> Reply:
        payload = envelope["payload"]
        shipment = payload["shipment"]
        if payload["quote_number"] != thread.get("quote_number"):
            reason = "The quote number is not known in this conversation."
            return self._decline(shipment["shipment_id"], reason, "forwarder")
        transport = shipment["transport"]
        missing = [key for key in ("etd", "eta") if transport[key] is None]
        if missing:  # 情報が足りないので、直して送り直してもらう
            issues = [
                Issue("REQUIRED_NULL", ("payload", "shipment", "transport", key)) for key in missing
            ]
            reply = error_payload("VALIDATION_FAILED", issues)
            return Reply(INPUT_REQUIRED, "error", reply, "forwarder")
        cutoff = date.fromisoformat(transport["etd"]) - timedelta(days=_CUTOFF_DAYS_BEFORE_ETD)
        thread["booking_number"] = self._next("BK")
        confirmation = {
            "shipment_id": shipment["shipment_id"],
            "booking_number": thread["booking_number"],
            "etd": transport["etd"],
            "eta": transport["eta"],
            "cargo_cutoff_at": f"{cutoff.isoformat()}T16:00:00+09:00",
            "note": None,
        }
        return Reply(COMPLETED, "booking_confirmation", confirmation, "forwarder")

    def _on_document_submission(self, envelope: dict[str, Any], thread: dict[str, Any]) -> Reply:
        shipment = envelope["payload"]["shipment"]
        found = find_discrepancies(shipment)
        if found:  # 書類の値が正本と違うので、直して送り直してもらう
            notice = {
                "shipment_id": shipment["shipment_id"],
                "discrepancies": found,
                "note": "Please correct the documents or the shipment data and submit again.",
            }
            return Reply(INPUT_REQUIRED, "discrepancy_notice", notice, "customs_broker")
        thread["draft_number"] = self._next("DD")
        draft = build_declaration_draft(shipment, thread["draft_number"])
        return Reply(COMPLETED, "declaration_draft", draft, "customs_broker")

    def _on_approval(self, envelope: dict[str, Any], thread: dict[str, Any]) -> Reply:
        if "draft_number" not in thread:
            reason = "No declaration draft is waiting for approval in this conversation."
            return self._decline(envelope["payload"]["shipment_id"], reason, "customs_broker")
        thread["approved"] = True
        return Reply(COMPLETED)

    def _on_rejection(self, envelope: dict[str, Any], thread: dict[str, Any]) -> Reply:
        thread["declined"] = True  # 相手が断ったことを控えるだけで、返事の封筒は出さない
        return Reply(COMPLETED)

    @staticmethod
    def _decline(shipment_id: str | None, reason: str, role: str) -> Reply:
        payload = {"shipment_id": shipment_id, "reason": reason, "note": None}
        return Reply(REJECTED, "rejection", payload, role)
