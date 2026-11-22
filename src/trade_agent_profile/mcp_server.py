"""MCP サーバー：検証、食い違いの一覧、申告の下書き（模擬）を、道具として出す。

荷主側が送る前に確かめるための道具（validate）と、通関業者側が書類を確かめるための
道具（list_discrepancies、draft_declaration）をまとめてある。AI は使わない。

起動（標準入出力でつなぐ）:
    uv run python -m trade_agent_profile.mcp_server
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from . import __version__, i18n
from .declaration import build_declaration_draft
from .issues import Issue
from .messages import is_message, validate_message
from .rules import DISCREPANCY_EVENT, find_discrepancies
from .validator import validate_shipment


def _notice() -> dict[str, str]:
    """必ず表示する2つの注意書き（文言の正本は locales/ にある）。"""
    return {
        lang: f"{i18n.catalog(lang)['ui']['notice']} {i18n.catalog(lang)['ui']['judge']}"
        for lang in i18n.LANGS
    }


INSTRUCTIONS = "\n".join(
    [
        "Tools for the trade-agent-profile: trade messages for AI agents on top of A2A and MCP. "
        "The tools only check data and copy values; they make no decisions. "
        "All checks are rule-based and no AI is used.",
        *(_notice()[lang] for lang in i18n.LANGS),
    ]
)

server = MCPServer("trade-agent-profile", instructions=INSTRUCTIONS, version=__version__)


def _blocking(shipment: Any) -> list[Issue]:
    """食い違いの記載漏れ以外の問題。これがあると、書類の値を正しく比べられない。"""
    errors = validate_shipment(shipment).errors
    return [issue for issue in errors if issue.code != "DISCREPANCY_NOT_RECORDED"]


@server.tool(
    description=(
        "Validate a shipment.json document (shared data contract v0.1) or a trade-agent-profile "
        "message envelope. Returns every problem with its code, path, and why/fix texts in "
        "Japanese and English. Codes such as country, currency and port are checked for format "
        "only. / shipment.json かメッセージ（封筒）を検証し、問題ごとに「どの項目が・なぜ違うか・"
        "どう直すか」を日本語と英語で返す。"
    )
)
def validate(document: dict[str, Any]) -> dict[str, Any]:
    kind = "message" if is_message(document) else "shipment"
    result = validate_message(document) if kind == "message" else validate_shipment(document)
    return {
        "kind": kind,
        "valid": result.valid,
        "errors": [issue.to_dict() for issue in result.errors],
        "notice": _notice(),
    }


@server.tool(
    description=(
        "List the values read from documents (documents[].fields) that differ from the "
        "authoritative top-level values of a shipment.json. Also tells whether a "
        "discrepancy_noted event is recorded. / 書類に書いてあった値のうち、正本（最上位の値）と"
        "違うものを一覧にする。"
    )
)
def list_discrepancies(shipment: dict[str, Any]) -> dict[str, Any]:
    blocking = _blocking(shipment)
    if blocking:
        return {
            "ok": False,
            "errors": [issue.to_dict() for issue in blocking],
            "count": 0,
            "discrepancies": [],
            "recorded_in_events": False,
            "notice": _notice(),
        }
    found = find_discrepancies(shipment)
    recorded = any(event["type"] == DISCREPANCY_EVENT for event in shipment["events"])
    return {
        "ok": True,
        "errors": [],
        "count": len(found),
        "discrepancies": found,
        "recorded_in_events": recorded,
        "notice": _notice(),
    }


@server.tool(
    description=(
        "Build a MOCK export declaration draft from a shipment.json by copying its authoritative "
        "values. It is not a customs declaration, nothing is filed, and commodity codes that have "
        "not been confirmed are listed under unverified. Refuses while documents still differ "
        "from the authoritative values. / shipment.json から申告の下書き（模擬）を作る。"
        "実際の申告ではない。"
    )
)
def draft_declaration(
    shipment: dict[str, Any], draft_number: str = "DD-MOCK-0001"
) -> dict[str, Any]:
    blocking = _blocking(shipment)
    if blocking:
        return {
            "ok": False,
            "reason": "invalid_shipment",
            "errors": [issue.to_dict() for issue in blocking],
            "discrepancies": [],
            "draft": None,
            "notice": _notice(),
        }
    found = find_discrepancies(shipment)
    if found:
        return {
            "ok": False,
            "reason": "discrepancies",
            "errors": [],
            "discrepancies": found,
            "draft": None,
            "notice": _notice(),
        }
    return {
        "ok": True,
        "reason": None,
        "errors": [],
        "discrepancies": [],
        "draft": build_declaration_draft(shipment, draft_number),
        "notice": _notice(),
    }


def main() -> None:
    server.run()  # 標準入出力（stdio）でつなぐ


if __name__ == "__main__":
    main()
