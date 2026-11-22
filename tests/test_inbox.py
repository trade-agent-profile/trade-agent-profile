"""受け付けの流れ：二重処理の防止、版が合わないとき、状態の対応。"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from test_messages import sample

from trade_agent_profile import validate_message
from trade_agent_profile.agents import BrokerAgent
from trade_agent_profile.demo import ScriptClock, ScriptIds, load_demo_shipment
from trade_agent_profile.inbox import (
    InboxStore,
    Outcome,
    Receiver,
    Reply,
    TaskClosedError,
    TaskNotFoundError,
)
from trade_agent_profile.messages import new_message
from trade_agent_profile.profile import COMPLETED, FAILED, INPUT_REQUIRED, REJECTED, TASK_STATES

SHIPPER = {"role": "shipper", "name": "Demo Resource Recovery Co., Ltd.", "id": "demo-shipper"}


class Desk:
    """テスト用の受付。相手側の見本と、決まった時計・識別子を組み合わせる。"""

    def __init__(self, handler: Any = None) -> None:
        self.broker = BrokerAgent()
        self.store = InboxStore()
        self.clock = ScriptClock("2026-12-01T09:00:00+09:00")
        self.ids = ScriptIds()
        self.receiver = Receiver(
            handler or self.broker,
            sender=self.broker.sender,
            store=self.store,
            clock=self.clock,
            new_id=self.ids,
        )

    def message(self, kind: str, payload: dict[str, Any], thread: str, **extra: Any) -> dict:
        return new_message(
            kind,
            payload,
            sender=SHIPPER,
            correlation_id=thread,
            sent_at=self.clock(),
            message_id=self.ids(),
            **extra,
        )


@pytest.fixture
def desk() -> Desk:
    return Desk()


def error_code(outcome: Outcome) -> str:
    assert outcome.status_message is not None
    assert outcome.status_message["message_type"] == "error"
    return outcome.status_message["payload"]["code"]


def test_same_message_id_is_not_processed_twice(desk: Desk) -> None:
    """M2 の完成条件：同じ message_id を2回送ると、2回目は処理されない。"""
    request = sample("quote_request")
    first = desk.receiver.receive(request)
    second = desk.receiver.receive(copy.deepcopy(request))

    assert desk.broker.calls == 1  # 相手側の処理は1回だけ
    assert desk.store.count() == 1
    assert first.state == COMPLETED and not first.duplicate
    assert second.duplicate
    assert (second.task_id, second.state, second.artifacts) == (
        first.task_id,
        first.state,
        first.artifacts,
    )
    assert second.artifacts[0]["payload"]["quote_number"] == "Q-0001"  # 見積番号も増えない


def test_same_message_id_with_other_content_is_refused(desk: Desk) -> None:
    request = sample("quote_request")
    desk.receiver.receive(request)
    changed = copy.deepcopy(request)
    changed["payload"]["note"] = "changed after sending"
    outcome = desk.receiver.receive(changed)

    assert outcome.state == REJECTED
    assert error_code(outcome) == "MESSAGE_ID_REUSED"
    assert desk.broker.calls == 1
    assert desk.store.count() == 1
    assert desk.receiver.receive(request).duplicate  # 最初の控えはそのまま残る


def test_processed_tells_a_resend_apart_before_anything_is_done(desk: Desk) -> None:
    """通信の部品が、タスクを探す前に再送を見分けるための問い合わせ。何も処理しない。"""
    request = sample("quote_request")
    assert desk.receiver.processed(request) is None  # まだ受け付けていない
    first = desk.receiver.receive(request)

    again = desk.receiver.processed(copy.deepcopy(request))
    assert again is not None and again.duplicate
    assert (again.task_id, again.state, again.artifacts) == (
        first.task_id,
        first.state,
        first.artifacts,
    )
    changed = copy.deepcopy(request)
    changed["payload"]["note"] = "changed after sending"
    assert desk.receiver.processed(changed) is None  # 中身が違えば、再送とはみなさない
    for other in ("text", None, {"message_id": 5}, {"message_id": "not-a-uuid"}):
        assert desk.receiver.processed(other) is None
    assert desk.broker.calls == 1 and desk.store.count() == 1


def test_resend_is_recognised_even_if_numbers_are_written_differently(desk: Desk) -> None:
    """JSON では 1 と 1.0 は同じ数。通信の途中で書き方が変わっても、再送と見分ける。"""
    request = sample("document_submission")
    first = desk.receiver.receive(request)
    rewritten = copy.deepcopy(request)
    for document in rewritten["payload"]["shipment"]["documents"]:
        for entry in document["fields"].values():
            entry["page"] = float(entry["page"]) if entry["page"] is not None else None
    second = desk.receiver.receive(rewritten)
    assert second.duplicate
    assert second.status_message == first.status_message
    assert desk.broker.calls == 1


@pytest.mark.parametrize(
    ("key", "value", "code"),
    [
        ("profile_version", "0.2.0", "PROFILE_VERSION_UNSUPPORTED"),
        ("profile", "other-profile", "PROFILE_UNKNOWN"),
    ],
)
def test_version_mismatch_is_rejected_without_processing(
    desk: Desk, key: str, value: str, code: str
) -> None:
    request = sample("quote_request")
    request[key] = value
    outcome = desk.receiver.receive(request)

    assert outcome.state == REJECTED
    assert error_code(outcome) == code
    assert outcome.status_message["payload"]["issues"] == [{"code": code, "path": key}]
    assert outcome.status_message["in_reply_to"] == request["message_id"]
    assert desk.broker.calls == 0


def test_invalid_content_asks_for_correction(desk: Desk) -> None:
    request = sample("quote_request")
    request["payload"]["shipment"]["status"] = "shipped"
    outcome = desk.receiver.receive(request)

    assert outcome.state == INPUT_REQUIRED
    assert error_code(outcome) == "VALIDATION_FAILED"
    issues = outcome.status_message["payload"]["issues"]
    assert issues == [{"code": "ENUM_INVALID", "path": "payload.shipment.status"}]
    assert desk.broker.calls == 0


@pytest.mark.parametrize("envelope", ["text", [], None, {"message_id": 5}])
def test_something_that_is_not_a_message_asks_for_correction(desk: Desk, envelope: Any) -> None:
    outcome = desk.receiver.receive(envelope)
    assert outcome.state == INPUT_REQUIRED
    assert error_code(outcome) == "VALIDATION_FAILED"
    assert "in_reply_to" not in outcome.status_message
    assert desk.store.count() == 0  # 識別子が使えないものは控えない


def test_message_type_the_receiver_does_not_handle(desk: Desk) -> None:
    outcome = desk.receiver.receive(sample("quote"))
    assert outcome.state == REJECTED
    assert error_code(outcome) == "UNEXPECTED_MESSAGE"


def test_unexpected_failure_is_reported_as_failed() -> None:
    def broken(envelope: dict[str, Any]) -> Reply:
        raise RuntimeError("boom")

    outcome = Desk(broken).receiver.receive(sample("quote_request"))
    assert outcome.state == FAILED
    assert error_code(outcome) == "INTERNAL_ERROR"
    assert "boom" not in str(outcome.status_message)  # 中の事情は相手に出さない


def test_input_required_task_continues_and_completed_task_is_closed(desk: Desk) -> None:
    thread = desk.ids()
    full = load_demo_shipment()
    wrong = copy.deepcopy(full)
    wrong["documents"][1]["fields"]["totals.gross_weight_kg"]["value"] = "21480.000"

    first = desk.receiver.receive(
        desk.message("document_submission", {"shipment": wrong, "note": None}, thread)
    )
    assert first.state == INPUT_REQUIRED
    notice = first.status_message
    assert notice["message_type"] == "discrepancy_notice"
    assert notice["sender"]["role"] == "customs_broker"
    assert notice["payload"]["discrepancies"] == [
        {
            "doc_type": "packing_list",
            "doc_number": "PL-0100",
            "path": "totals.gross_weight_kg",
            "document_value": "21480.000",
            "authoritative_value": "21840.000",
        }
    ]

    again = desk.message(
        "document_submission",
        {"shipment": full, "note": None},
        thread,
        in_reply_to=notice["message_id"],
    )
    second = desk.receiver.receive(again, first.task_id)
    assert second.task_id == first.task_id  # 同じタスクの続き
    assert second.state == COMPLETED
    assert second.artifacts[0]["message_type"] == "declaration_draft"

    more = desk.message("document_submission", {"shipment": full, "note": None}, thread)
    with pytest.raises(TaskClosedError):
        desk.receiver.receive(more, first.task_id)  # 終わったタスクには続きを送れない
    with pytest.raises(TaskNotFoundError):
        desk.receiver.receive(more, "no-such-task")


def test_booking_with_unknown_quote_and_approval_without_draft_are_declined(desk: Desk) -> None:
    booking = desk.receiver.receive(sample("booking_request"))  # この会話では見積を出していない
    assert booking.state == REJECTED
    assert booking.status_message["message_type"] == "rejection"

    approval = desk.receiver.receive(sample("approval"))
    assert approval.state == REJECTED
    assert approval.status_message["message_type"] == "rejection"
    assert approval.status_message["sender"]["role"] == "customs_broker"


def test_booking_without_schedule_asks_for_it(desk: Desk) -> None:
    thread = desk.ids()
    planned = sample("quote_request")["payload"]["shipment"]
    quote = desk.receiver.receive(
        desk.message("quote_request", {"shipment": planned, "reply_by": None, "note": None}, thread)
    ).artifacts[0]
    planned["transport"]["etd"] = None
    payload = {"shipment": planned, "quote_number": quote["payload"]["quote_number"], "note": None}
    outcome = desk.receiver.receive(desk.message("booking_request", payload, thread))

    assert outcome.state == INPUT_REQUIRED
    assert outcome.status_message["payload"]["issues"] == [
        {"code": "REQUIRED_NULL", "path": "payload.shipment.transport.etd"}
    ]


def test_every_reply_is_itself_a_valid_message(desk: Desk) -> None:
    outcomes = [
        desk.receiver.receive(sample("quote_request")),
        desk.receiver.receive(sample("quote")),
        desk.receiver.receive(sample("approval")),
        desk.receiver.receive("text"),
    ]
    for outcome in outcomes:
        assert outcome.state in TASK_STATES
        for message in [*outcome.artifacts, outcome.status_message]:
            if message is not None:
                result = validate_message(message)
                assert result.valid, [(issue.code, issue.path) for issue in result.errors]


def test_store_keeps_results_in_a_file(tmp_path) -> None:
    path = str(tmp_path / "inbox.sqlite3")
    first = InboxStore(path)
    outcome = Outcome("task-1", COMPLETED, "2026-12-01T09:00:00+09:00", [{"a": "あ"}])
    first.put("id-1", "fingerprint", outcome)
    first.close()

    second = InboxStore(path)  # 開き直しても、控えが残っている
    assert second.get("id-1") == ("fingerprint", outcome)
    assert second.get("id-2") is None
    second.close()
