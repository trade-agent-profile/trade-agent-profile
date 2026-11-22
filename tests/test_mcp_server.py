"""MCP サーバー：3つの道具（検証・食い違いの一覧・申告の下書き）が、決めた形で答えること。"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from typing import Any

import pytest
from conftest import ROOT, SAMPLES, load_json
from mcp import Client, StdioServerParameters

from trade_agent_profile import i18n
from trade_agent_profile.demo import load_demo_shipment
from trade_agent_profile.mcp_server import server

TOOLS = ["validate", "list_discrepancies", "draft_declaration"]
WRONG_GROSS_WEIGHT = "21480.000"  # 正本は 21840.000


def call(name: str, arguments: dict[str, Any]) -> Any:
    """道具を1回呼ぶ（同じプログラムの中で、MCP の決まりどおりにつないで呼ぶ）。"""

    async def go() -> Any:
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(go())


def answer(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = call(name, arguments)
    assert not result.is_error, result.content
    # 同じ答えが、文字の形（content）と、項目に分かれた形の両方で返る
    assert json.loads(result.content[0].text) == result.structured_content
    return result.structured_content


def with_wrong_packing_list(shipment: dict[str, Any]) -> dict[str, Any]:
    """パッキングリストの総重量だけを、正本と違う値にした写し。"""
    changed = copy.deepcopy(shipment)
    for document in changed["documents"]:
        if document["doc_type"] == "packing_list":
            document["fields"]["totals.gross_weight_kg"]["value"] = WRONG_GROSS_WEIGHT
            return changed
    raise AssertionError("見本にパッキングリストがありません")


def pairs(errors: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(error["code"], error["path"]) for error in errors]


def test_server_offers_three_tools_with_descriptions_in_both_languages() -> None:
    async def go() -> Any:
        async with Client(server) as client:
            return await client.list_tools(), client.server_info, client.instructions

    listed, info, instructions = asyncio.run(go())
    assert [tool.name for tool in listed.tools] == TOOLS
    assert info.name == "trade-agent-profile"
    for lang in i18n.LANGS:  # つないだ相手に、最初に必ず伝わる注意書き
        ui = i18n.catalog(lang)["ui"]
        assert ui["notice"] in instructions and ui["judge"] in instructions
    for tool in listed.tools:
        assert " / " in tool.description  # 英語と日本語の両方で説明している
        required = tool.input_schema["required"]
        assert required == (["document"] if tool.name == "validate" else ["shipment"])


def test_validate_accepts_a_correct_shipment(base: dict[str, Any]) -> None:
    result = answer("validate", {"document": base})
    assert result["kind"] == "shipment"
    assert result["valid"] is True
    assert result["errors"] == []
    for lang in i18n.LANGS:
        ui = i18n.catalog(lang)["ui"]
        assert ui["notice"] in result["notice"][lang]
        assert ui["judge"] in result["notice"][lang]


@pytest.mark.parametrize(
    "name", ["01_required_missing", "05_total_mismatch", "10_discrepancy_not_recorded"]
)
def test_validate_reports_the_same_code_and_place_as_the_command(name: str) -> None:
    expected = load_json(SAMPLES / "invalid" / f"{name}.expected.json")
    result = answer("validate", {"document": load_json(SAMPLES / "invalid" / f"{name}.json")})
    assert result["valid"] is False
    assert pairs(result["errors"]) == pairs(expected["errors"])
    first = result["errors"][0]
    for lang in i18n.LANGS:  # なぜ違うか・どう直すかが、日本語と英語の両方で返る
        assert first["why"][lang] and first["fix"][lang]


def test_validate_recognises_a_message() -> None:
    message = load_json(SAMPLES / "messages" / "02_quote.json")
    result = answer("validate", {"document": message})
    assert (result["kind"], result["valid"]) == ("message", True)

    del message["payload"]["total"]
    result = answer("validate", {"document": message})
    assert result["kind"] == "message"
    assert result["valid"] is False
    assert ("REQUIRED_MISSING", "payload.total") in pairs(result["errors"])


def test_validate_refuses_something_that_is_not_a_json_object() -> None:
    result = call("validate", {"document": "not an object"})
    assert result.is_error


def test_list_discrepancies_is_empty_when_documents_match() -> None:
    result = answer("list_discrepancies", {"shipment": load_demo_shipment()})
    assert result["ok"] is True
    assert result["count"] == 0
    assert result["discrepancies"] == []


def test_list_discrepancies_shows_both_values_for_a_difference() -> None:
    shipment = with_wrong_packing_list(load_demo_shipment())
    result = answer("list_discrepancies", {"shipment": shipment})
    assert result["ok"] is True
    assert result["count"] == 1
    found = result["discrepancies"][0]
    assert found["doc_type"] == "packing_list"
    assert found["path"] == "totals.gross_weight_kg"
    assert found["document_value"] == WRONG_GROSS_WEIGHT
    assert found["authoritative_value"] == shipment["totals"]["gross_weight_kg"]
    assert result["recorded_in_events"] is False  # 記録（events）にまだ書いていない


def test_list_discrepancies_tells_when_the_difference_is_already_recorded() -> None:
    shipment = load_json(SAMPLES / "valid" / "09_sea_cif_1c_2l_discrepancy_noted.json")
    result = answer("list_discrepancies", {"shipment": shipment})
    assert result["ok"] is True
    assert result["count"] >= 1
    assert result["recorded_in_events"] is True


def test_list_discrepancies_does_not_compare_a_broken_shipment() -> None:
    shipment = load_json(SAMPLES / "invalid" / "05_total_mismatch.json")
    result = answer("list_discrepancies", {"shipment": shipment})
    assert result["ok"] is False
    assert pairs(result["errors"]) == [("TOTAL_MISMATCH", "totals.amount")]
    assert result["discrepancies"] == []


def test_draft_declaration_is_a_mock_that_copies_the_authoritative_values() -> None:
    shipment = load_demo_shipment()
    result = answer("draft_declaration", {"shipment": shipment})
    assert result["ok"] is True
    draft = result["draft"]
    assert draft["mock"] is True
    assert draft["draft_number"] == "DD-MOCK-0001"
    assert draft["invoice_amount"] == shipment["totals"]["amount"]
    assert draft["unverified"] == ["lines[0].hs_code_jp", "lines[1].hs_code_jp"]
    assert "not a customs declaration" in draft["note"]
    assert i18n.catalog("ja")["ui"]["judge"] in result["notice"]["ja"]


def test_draft_declaration_waits_while_documents_differ() -> None:
    shipment = with_wrong_packing_list(load_demo_shipment())
    result = answer("draft_declaration", {"shipment": shipment, "draft_number": "DD-TEST-1"})
    assert result["ok"] is False
    assert result["reason"] == "discrepancies"
    assert result["draft"] is None
    assert [item["path"] for item in result["discrepancies"]] == ["totals.gross_weight_kg"]


def test_draft_declaration_refuses_a_broken_shipment() -> None:
    shipment = load_json(SAMPLES / "invalid" / "01_required_missing.json")
    result = answer("draft_declaration", {"shipment": shipment})
    assert result["ok"] is False
    assert result["reason"] == "invalid_shipment"
    assert result["draft"] is None
    assert result["errors"]


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_server_answers_over_stdio(mode: str, base: dict[str, Any]) -> None:
    """別のプログラムとして起動し、標準入出力でつないで呼ぶ（Claude Code などと同じつなぎ方）。

    auto は MCP の新しい版、legacy はひとつ前の版のつなぎ方。
    """
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "trade_agent_profile.mcp_server"], cwd=str(ROOT)
    )

    async def go() -> Any:
        async with Client(parameters, mode=mode) as client:
            listed = await client.list_tools()
            result = await client.call_tool("validate", {"document": base})
            return listed, result, client.protocol_version

    listed, result, version = asyncio.run(go())
    assert version == {"auto": "2026-07-28", "legacy": "2025-11-25"}[mode]  # MCP の版
    assert [tool.name for tool in listed.tools] == TOOLS
    assert not result.is_error
    assert result.structured_content["valid"] is True


def test_project_setting_starts_this_server() -> None:
    """.mcp.json（Claude Code がこのフォルダで読む設定）が、このサーバーを指していること。"""
    setting = load_json(ROOT / ".mcp.json")["mcpServers"]["trade-agent-profile"]
    assert setting["command"] == "uv"
    assert setting["args"] == ["run", "python", "-m", "trade_agent_profile.mcp_server"]
