"""メッセージ（封筒と10種類の中身）の検証と組み立て。

封筒の必須項目は profile, profile_version, message_type, message_id, correlation_id,
sent_at, sender, payload。どのメッセージへの返事かを示す in_reply_to だけは省ける。
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .issues import Issue, ValidationResult
from .profile import PROFILE, PROFILE_VERSION, REPLY_TYPES, SUPPORTED_PROFILE_VERSIONS
from .validator import read_json, schema_issues, schema_validator, validate_shipment

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

# 中身（payload）にある日付と日時。形式はスキーマで調べ、実在するかをここで調べる
_DATES = {
    "quote_request": (("reply_by", "date"),),
    "quote": (("valid_until", "date"),),
    "booking_confirmation": (("etd", "date"), ("eta", "date"), ("cargo_cutoff_at", "datetime")),
    "declaration_draft": (("etd", "date"),),
}
# 受け手が discrepancy_notice で答える誤りは、メッセージの検証ではエラーにしない
_LEFT_TO_RECEIVER = {"document_submission": ("DISCREPANCY_NOT_RECORDED",)}


def is_message(data: Any) -> bool:
    """データがメッセージ（封筒）かどうかを、項目から見分ける。"""
    return isinstance(data, dict) and ("message_type" in data or "profile" in data)


def validate_message(data: Any) -> ValidationResult:
    """読み込み済みのメッセージ（辞書）を検証する。

    流れは shipment.json と同じ：プロファイルと版 → スキーマ → 規則。
    中身に shipment があれば、共通データ契約の検証もあわせて行う。
    """
    if not isinstance(data, dict):
        return ValidationResult([Issue("ROOT_NOT_OBJECT")])

    profile = data.get("profile")
    if isinstance(profile, str) and profile != PROFILE:
        params = {"value": profile, "expected": PROFILE}
        return ValidationResult([Issue("PROFILE_UNKNOWN", ("profile",), params)])

    version = data.get("profile_version")
    version = version if isinstance(version, str) else None
    if version and _VERSION_RE.match(version) and version not in SUPPORTED_PROFILE_VERSIONS:
        params = {"value": version, "supported": ", ".join(SUPPORTED_PROFILE_VERSIONS)}
        return ValidationResult(
            [Issue("PROFILE_VERSION_UNSUPPORTED", ("profile_version",), params)]
        )

    issues = schema_issues(data, schema_validator("message"))
    if not issues:
        issues = _message_rules(data)
    return ValidationResult(issues)


def validate_any_file(path: str | Path) -> ValidationResult:
    """ファイルを読み、中身に応じて shipment.json かメッセージとして検証する。"""
    data, problem = read_json(path)
    if problem is not None:
        return ValidationResult([problem])
    return validate_message(data) if is_message(data) else validate_shipment(data)


def new_message(
    message_type: str,
    payload: dict[str, Any],
    *,
    sender: dict[str, str],
    correlation_id: str,
    sent_at: str,
    message_id: str | None = None,
    in_reply_to: str | None = None,
) -> dict[str, Any]:
    """封筒を組み立てる。message_id を渡さなければ、新しい UUID を振る。"""
    envelope: dict[str, Any] = {
        "profile": PROFILE,
        "profile_version": PROFILE_VERSION,
        "message_type": message_type,
        "message_id": message_id or str(uuid.uuid4()),
        "correlation_id": correlation_id,
    }
    if in_reply_to is not None:
        envelope["in_reply_to"] = in_reply_to
    envelope["sent_at"] = sent_at
    envelope["sender"] = dict(sender)
    envelope["payload"] = payload
    return envelope


def normalize_numbers(value: Any) -> Any:
    """小数部が 0 の数を整数にそろえる（18.0 → 18）。

    JSON では 18 と 18.0 は同じ数。通信の方式によっては、数がすべて小数つきの形で届く
    （A2A の Part の data など）ので、比べる前と、受け取ったあとにそろえる。
    """
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: normalize_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_numbers(item) for item in value]
    return value


def digest(envelope: Any) -> str:
    """封筒の中身の指紋。同じ message_id で中身が違う送信を見分けるのに使う。

    JSON の値として同じなら、同じ指紋になる（項目の並び順や、18 と 18.0 の違いは問わない）。
    """
    text = json.dumps(
        normalize_numbers(envelope), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _exists(value: str, kind: str) -> bool:
    """形式の合った日付・日時が、暦や時計に実在するか。"""
    try:
        (date if kind == "date" else datetime).fromisoformat(value)
    except ValueError:
        return False
    return True


def _check_sum(
    items: list[dict[str, Any]], written: str, where: tuple[str, str], issues: list[Issue]
) -> None:
    expected = sum((Decimal(item["amount"]) for item in items), Decimal(0))
    if expected != Decimal(written):
        params = {"expected": f"{expected:.2f}", "actual": written}
        issues.append(Issue("TOTAL_MISMATCH", where, params))


def _message_rules(data: dict[str, Any]) -> list[Issue]:
    """スキーマでは表せない決まり。スキーマに合格したメッセージだけを受け取る。"""
    issues: list[Issue] = []
    kind = data["message_type"]
    payload = data["payload"]

    if not _exists(data["sent_at"], "datetime"):
        params = {"value": data["sent_at"], "kind": "datetime_calendar"}
        issues.append(Issue("FORMAT_INVALID", ("sent_at",), params))
    if kind in REPLY_TYPES and data.get("in_reply_to") is None:
        issues.append(Issue("IN_REPLY_TO_REQUIRED", ("in_reply_to",), {"message_type": kind}))

    for key, date_kind in _DATES.get(kind, ()):
        value = payload[key]
        if value is not None and not _exists(value, date_kind):
            params = {"value": value, "kind": f"{date_kind}_calendar"}
            issues.append(Issue("FORMAT_INVALID", ("payload", key), params))

    if "shipment" in payload:
        skipped = _LEFT_TO_RECEIVER.get(kind, ())
        for issue in validate_shipment(payload["shipment"]).errors:
            if issue.code not in skipped:
                parts = ("payload", "shipment", *issue.parts)
                issues.append(Issue(issue.code, parts, issue.params))

    if kind == "quote":
        _check_sum(payload["charges"], payload["total"], ("payload", "total"), issues)
    elif kind == "declaration_draft":
        where = ("payload", "invoice_amount")
        _check_sum(payload["lines"], payload["invoice_amount"], where, issues)
    elif kind == "booking_confirmation":
        etd, eta = payload["etd"], payload["eta"]
        if _exists(etd, "date") and _exists(eta, "date"):
            if date.fromisoformat(eta) < date.fromisoformat(etd):
                issues.append(Issue("DATE_ORDER", ("payload", "eta"), {"etd": etd, "eta": eta}))
    return issues
