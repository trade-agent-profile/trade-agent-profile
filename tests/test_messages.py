"""メッセージ（封筒と10種類の中身）の検証。見本を1か所ずつ変えて、出るエラーを確かめる。"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import SAMPLES, load_json
from test_validator import _UNFILLED, Change, _schema_paths, delp, setp

from trade_agent_profile import i18n, load_schema, validate_message
from trade_agent_profile.profile import MESSAGE_TYPES
from trade_agent_profile.validator import schema_validator

MESSAGES = sorted((SAMPLES / "messages").glob("*.json"))
UPPER_UUID = "5B0C0C5E-0C1E-4F6A-9D2B-3A1F0E7C9D10"


def sample(kind: str) -> dict[str, Any]:
    """種類を指定して、見本のメッセージを新しく読む。"""
    return load_json(next(path for path in MESSAGES if path.stem.split("_", 1)[1] == kind))


def test_there_is_one_sample_per_message_type() -> None:
    assert tuple(path.stem.split("_", 1)[1] for path in MESSAGES) == MESSAGE_TYPES
    assert len(MESSAGE_TYPES) == 10


@pytest.mark.parametrize("kind", MESSAGE_TYPES)
def test_samples_are_valid(kind: str) -> None:
    data = sample(kind)
    assert data["message_type"] == kind
    result = validate_message(data)
    assert result.valid, [(issue.code, issue.path) for issue in result.errors]
    # スキーマだけでも合格する（ほかの人がスキーマだけで調べる場合のため）
    assert schema_validator("message").is_valid(data)


CASES: list[tuple[str, str, list[Change], set[tuple[str, str]]]] = [
    # 封筒
    (
        "必須項目がない",
        "quote_request",
        [delp("correlation_id")],
        {("REQUIRED_MISSING", "correlation_id")},
    ),
    (
        "message_id が UUID でない",
        "quote_request",
        [setp("message_id", "not-a-uuid")],
        {("FORMAT_INVALID", "message_id")},
    ),
    (
        "message_id が大文字",
        "quote_request",
        [setp("message_id", UPPER_UUID)],
        {("FORMAT_INVALID", "message_id")},
    ),
    (
        "知らない種類",
        "quote_request",
        [setp("message_type", "inquiry")],
        {("ENUM_INVALID", "message_type")},
    ),
    (
        "知らない立場",
        "quote_request",
        [setp("sender.role", "carrier")],
        {("ENUM_INVALID", "sender.role")},
    ),
    (
        "日時の形が違う",
        "quote_request",
        [setp("sent_at", "2026-12-01 09:00")],
        {("FORMAT_INVALID", "sent_at")},
    ),
    (
        "実在しない日時",
        "quote_request",
        [setp("sent_at", "2026-12-01T25:00:00+09:00")],
        {("FORMAT_INVALID", "sent_at")},
    ),
    ("封筒に知らない項目", "quote_request", [setp("extra", "x")], {("UNKNOWN_FIELD", "extra")}),
    ("中身がオブジェクトでない", "quote", [setp("payload", "x")], {("TYPE_MISMATCH", "payload")}),
    (
        "ほかのプロファイル",
        "quote_request",
        [setp("profile", "other-profile")],
        {("PROFILE_UNKNOWN", "profile")},
    ),
    (
        "扱えない版",
        "quote_request",
        [setp("profile_version", "0.2.0")],
        {("PROFILE_VERSION_UNSUPPORTED", "profile_version")},
    ),
    (
        "扱えない版なら、ほかの検査はしない",
        "quote_request",
        [setp("profile_version", "1.0.0"), setp("message_type", "inquiry")],
        {("PROFILE_VERSION_UNSUPPORTED", "profile_version")},
    ),
    # 返事の相手
    (
        "最初のメッセージは in_reply_to が null でよい",
        "quote_request",
        [setp("in_reply_to", None)],
        set(),
    ),
    (
        "返事なのに in_reply_to がない",
        "quote",
        [delp("in_reply_to")],
        {("IN_REPLY_TO_REQUIRED", "in_reply_to")},
    ),
    (
        "承認なのに in_reply_to がない",
        "approval",
        [delp("in_reply_to")],
        {("IN_REPLY_TO_REQUIRED", "in_reply_to")},
    ),
    ("エラーは in_reply_to がなくてもよい", "error", [delp("in_reply_to")], set()),
    # 中身
    (
        "中身の必須項目がない",
        "quote_request",
        [delp("payload.reply_by")],
        {("REQUIRED_MISSING", "payload.reply_by")},
    ),
    (
        "中身に知らない項目",
        "approval",
        [setp("payload.comment", "x")],
        {("UNKNOWN_FIELD", "payload.comment")},
    ),
    (
        "実在しない日付",
        "quote_request",
        [setp("payload.reply_by", "2026-02-30")],
        {("FORMAT_INVALID", "payload.reply_by")},
    ),
    (
        "中の shipment の誤り",
        "quote_request",
        [setp("payload.shipment.status", "shipped")],
        {("ENUM_INVALID", "payload.shipment.status")},
    ),
    (
        "見積の合計が合わない",
        "quote",
        [setp("payload.total", "1.00")],
        {("TOTAL_MISMATCH", "payload.total")},
    ),
    ("料金が0件", "quote", [setp("payload.charges", [])], {("ARRAY_LENGTH", "payload.charges")}),
    (
        "料金が数値",
        "quote",
        [setp("payload.charges[0].amount", 85000)],
        {("TYPE_MISMATCH", "payload.charges[0].amount")},
    ),
    (
        "到着が出発より前",
        "booking_confirmation",
        [setp("payload.eta", "2026-12-01")],
        {("DATE_ORDER", "payload.eta")},
    ),
    (
        "書類の食い違いは受け手が答えるので、検証では通す",
        "document_submission",
        [],
        set(),
    ),
    (
        "書類の提出でも、ほかの誤りはエラー",
        "document_submission",
        [setp("payload.shipment.totals.packages", 1)],
        {("TOTAL_MISMATCH", "payload.shipment.totals.packages")},
    ),
    (
        "食い違いが0件",
        "discrepancy_notice",
        [setp("payload.discrepancies", [])],
        {("ARRAY_LENGTH", "payload.discrepancies")},
    ),
    (
        "模擬の印がない下書き",
        "declaration_draft",
        [setp("payload.mock", False)],
        {("ENUM_INVALID", "payload.mock")},
    ),
    (
        "下書きの金額が明細と合わない",
        "declaration_draft",
        [setp("payload.invoice_amount", "1.00")],
        {("TOTAL_MISMATCH", "payload.invoice_amount")},
    ),
    ("理由が空", "rejection", [setp("payload.reason", "")], {("EMPTY_VALUE", "payload.reason")}),
    (
        "知らないエラーの種類",
        "error",
        [setp("payload.code", "OOPS")],
        {("ENUM_INVALID", "payload.code")},
    ),
]


@pytest.mark.parametrize(
    ("kind", "changes", "expected"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_message_rules(kind: str, changes: list[Change], expected: set[tuple[str, str]]) -> None:
    data = sample(kind)
    for change in changes:
        change(data)
    result = validate_message(data)
    assert {(issue.code, issue.path) for issue in result.errors} == expected
    for issue in result.errors:
        for lang in i18n.LANGS:
            for text in (issue.why(lang), issue.fix(lang)):
                assert text
                assert not _UNFILLED.search(text), text


def test_wrong_content_for_the_type_is_rejected() -> None:
    data = sample("approval")
    data["payload"] = sample("rejection")["payload"]
    codes = {(issue.code, issue.path) for issue in validate_message(data).errors}
    assert ("UNKNOWN_FIELD", "payload.reason") in codes
    assert not schema_validator("message").is_valid(data)


def test_labels_inside_the_shipment_use_the_contract_names() -> None:
    data = sample("quote_request")
    data["payload"]["shipment"]["status"] = "shipped"
    labels = {issue.path: issue.label("ja") for issue in validate_message(data).errors}
    assert labels == {"payload.shipment.status": "状態"}

    data = sample("quote_request")
    data["sender"]["role"] = "carrier"
    labels = {issue.path: issue.label("ja") for issue in validate_message(data).errors}
    assert labels == {"sender.role": "送り手の立場"}


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_every_message_item_has_a_label(lang: str) -> None:
    schema = load_schema("message")
    paths = _schema_paths(schema, schema)
    for name, definition in schema["$defs"].items():
        if name.startswith("payload_"):
            paths |= _schema_paths(definition, schema, "payload")
    assert paths == set(i18n.catalog(lang)["message_fields"])


def test_every_message_format_kind_has_a_message() -> None:
    definitions = load_schema("message")["$defs"].values()
    kinds = {definition["x-kind"] for definition in definitions if "x-kind" in definition}
    for lang in i18n.LANGS:
        assert kinds <= set(i18n.catalog(lang)["kinds"])


def _shape(value: Any) -> Any:
    return {key: _shape(item) for key, item in value.items()} if isinstance(value, dict) else "text"


def test_japanese_and_english_catalogs_have_the_same_shape() -> None:
    assert _shape(i18n.catalog("ja")) == _shape(i18n.catalog("en"))


def test_the_ten_types_in_schema_and_code_agree() -> None:
    schema = load_schema("message")
    assert tuple(schema["properties"]["message_type"]["enum"]) == MESSAGE_TYPES
    payloads = {
        name.removeprefix("payload_") for name in schema["$defs"] if name.startswith("payload_")
    }
    assert payloads == set(MESSAGE_TYPES)
    assert set(schema["$defs"]["payload_error"]["properties"]["code"]["enum"]) == set(
        i18n.catalog("ja")["message_errors"]
    )
