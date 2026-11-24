"""スキーマでは表せない決まりの検査。

スキーマに合格したデータだけを受け取る（形と型はもう確かめてある前提）。
ここで調べるもの：日付が実在するか、日付の前後、コンテナ番号の検査数字、
明細とコンテナの対応、合計の一致、書類の値と正本の食い違いの記録。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from . import iso6346
from .issues import Issue
from .paths import parse_field_path, resolve

# 食い違いを確認したことを表す出来事の種類（events[].type）
DISCREPANCY_EVENT = "discrepancy_noted"

# 書類の値と比べてよい、正本の項目の入口
_FIELD_ROOTS = (
    "shipment_id",
    "direction",
    "status",
    "parties",
    "trade_terms",
    "transport",
    "lines",
    "totals",
)
# 数として比べる項目（"22500.0" と "22500.00" を同じとみなす）
_DECIMAL_LEAVES = (
    "amount",
    "quantity",
    "net_weight_kg",
    "gross_weight_kg",
    "unit_price",
    "freight_amount",  # 0.1.1 で足した項目
    "insurance_premium_amount",  # 同上
)
_NUMBER_RE = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")


def run_rules(data: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    _check_dates(data, issues)
    _check_parties(data, issues)
    _check_containers(data, issues)
    _check_lines(data, issues)
    _check_totals(data, issues)
    _check_documents(data, issues)
    return issues


def _parse_date(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _check_dates(data: dict[str, Any], issues: list[Issue]) -> None:
    transport = data["transport"]
    parsed: dict[str, date | None] = {}
    for key in ("etd", "eta"):
        value = transport[key]
        if value is None:
            continue
        parsed[key] = _parse_date(value)
        if parsed[key] is None:
            params = {"value": value, "kind": "date_calendar"}
            issues.append(Issue("FORMAT_INVALID", ("transport", key), params))
    etd, eta = parsed.get("etd"), parsed.get("eta")
    if etd and eta and eta < etd:
        params = {"etd": transport["etd"], "eta": transport["eta"]}
        issues.append(Issue("DATE_ORDER", ("transport", "eta"), params))

    for index, document in enumerate(data["documents"]):
        value = document["issue_date"]
        if value is not None and _parse_date(value) is None:
            params = {"value": value, "kind": "date_calendar"}
            issues.append(Issue("FORMAT_INVALID", ("documents", index, "issue_date"), params))

    for index, event in enumerate(data["events"]):
        try:
            datetime.fromisoformat(event["at"])
        except ValueError:
            params = {"value": event["at"], "kind": "datetime_calendar"}
            issues.append(Issue("FORMAT_INVALID", ("events", index, "at"), params))


def _check_parties(data: dict[str, Any], issues: list[Issue]) -> None:
    if data["direction"] == "export" and data["parties"]["exporter"] is None:
        issues.append(Issue("EXPORTER_REQUIRED", ("parties", "exporter")))


def _check_containers(data: dict[str, Any], issues: list[Issue]) -> None:
    seen: set[str] = set()
    for index, container in enumerate(data["transport"]["containers"]):
        number = container["number"]
        where = ("transport", "containers", index, "number")
        expected, actual = iso6346.check_digit(number[:10]), int(number[10])
        if expected != actual:
            params = {"value": number, "expected": expected, "actual": actual}
            issues.append(Issue("CONTAINER_CHECK_DIGIT", where, params))
        if number in seen:
            issues.append(Issue("CONTAINER_DUPLICATE", where, {"value": number}))
        seen.add(number)


def _check_lines(data: dict[str, Any], issues: list[Issue]) -> None:
    containers = {container["number"] for container in data["transport"]["containers"]}
    seen: set[int] = set()
    for index, line in enumerate(data["lines"]):
        line_no = line["line_no"]
        if line_no in seen:
            issues.append(
                Issue("LINE_NO_DUPLICATE", ("lines", index, "line_no"), {"value": line_no})
            )
        seen.add(line_no)
        number = line["container_number"]
        if number is not None and number not in containers:
            where = ("lines", index, "container_number")
            issues.append(Issue("LINE_CONTAINER_UNKNOWN", where, {"value": number}))


def _check_totals(data: dict[str, Any], issues: list[Issue]) -> None:
    """明細の合計と totals を比べる。明細か合計に null があるものは比べない。"""
    lines, totals = data["lines"], data["totals"]
    for key, places in (("amount", 2), ("net_weight_kg", 3), ("gross_weight_kg", 3)):
        written = totals[key]
        values = [line[key] for line in lines]
        if written is None or any(value is None for value in values):
            continue
        expected = sum((Decimal(value) for value in values), Decimal(0))
        if expected != Decimal(written):
            params = {"expected": f"{expected:.{places}f}", "actual": written}
            issues.append(Issue("TOTAL_MISMATCH", ("totals", key), params))

    written = totals["packages"]
    counts = [line["packages"] for line in lines]
    if written is not None and all(count is not None for count in counts):
        expected_count = sum(counts)
        if expected_count != written:
            params = {"expected": expected_count, "actual": written}
            issues.append(Issue("TOTAL_MISMATCH", ("totals", "packages"), params))


def _check_documents(data: dict[str, Any], issues: list[Issue]) -> None:
    recorded = any(event["type"] == DISCREPANCY_EVENT for event in data["events"])
    for index, document in enumerate(data["documents"]):
        for key, entry in document["fields"].items():
            where = ("documents", index, "fields", key)
            if entry["extracted_by"] == "ai" and entry["confidence"] is None:
                issues.append(Issue("CONFIDENCE_REQUIRED", (*where, "confidence")))
            bbox = entry["bbox"]
            if bbox is not None and not _bbox_ok(bbox):
                issues.append(Issue("BBOX_INVALID", (*where, "bbox"), {"value": bbox}))

            reason, authoritative = _resolve_field(data, key)
            if reason:
                issues.append(Issue("FIELD_PATH_INVALID", where, {"key": key, "reason": reason}))
                continue
            if authoritative is None:
                continue  # 正本がまだ決まっていない値とは比べない
            if not _same(key, entry["value"], authoritative) and not recorded:
                params = {
                    "doc_value": entry["value"],
                    "auth_value": authoritative,
                    "field": key,
                }
                issues.append(Issue("DISCREPANCY_NOT_RECORDED", where, params))


def find_discrepancies(data: dict[str, Any]) -> list[dict[str, Any]]:
    """書類に書いてあった値のうち、正本と違うものを並べる。

    記録（events）があるかどうかは見ない。形の整ったデータを受け取る前提。
    """
    found: list[dict[str, Any]] = []
    for document in data["documents"]:
        for key, entry in document["fields"].items():
            reason, authoritative = _resolve_field(data, key)
            if reason or authoritative is None:
                continue
            if not _same(key, entry["value"], authoritative):
                found.append(
                    {
                        "doc_type": document["doc_type"],
                        "doc_number": document["doc_number"],
                        "path": key,
                        "document_value": entry["value"],
                        "authoritative_value": authoritative,
                    }
                )
    return found


def _bbox_ok(bbox: list[float]) -> bool:
    x0, top, x1, bottom = bbox
    return min(bbox) >= 0 and x0 <= x1 and top <= bottom


def _resolve_field(data: dict[str, Any], key: str) -> tuple[str | None, Any]:
    """fields のキーが指す正本の値を返す。指せないときは理由を返す。"""
    parts = parse_field_path(key)
    if parts is None:
        return "syntax", None
    if parts[0] not in _FIELD_ROOTS:
        return "not_allowed", None
    found, value = resolve(data, parts)
    if not found:
        return "not_found", None
    if isinstance(value, dict | list):
        return "not_scalar", None
    return None, value


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str) and _NUMBER_RE.match(value):
        return Decimal(value)
    return None


def _same(key: str, document_value: Any, authoritative: Any) -> bool:
    """書類の値と正本の値が同じかどうか。金額や重量は数として比べる。"""
    parts = parse_field_path(key) or []
    leaf = parts[-1] if parts else None
    is_number = isinstance(authoritative, int | float) and not isinstance(authoritative, bool)
    if is_number or leaf in _DECIMAL_LEAVES:
        left, right = _as_decimal(document_value), _as_decimal(authoritative)
        if left is not None and right is not None:
            return left == right
    return type(document_value) is type(authoritative) and document_value == authoritative
