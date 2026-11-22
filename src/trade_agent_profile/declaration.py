"""申告の下書き（模擬）。正本の値を写すだけで、判断はしない。

実際の輸出申告ではない。品目番号など、出典で確かめていない値は「未確認」として並べる。
判断するのは利用者です。このツールは下調べと記録を担います。
"""

from __future__ import annotations

from typing import Any

MOCK_NOTE = (
    "Mock draft for demonstrating the data flow. It is not a customs declaration and nothing "
    "has been filed. Items listed in unverified must be confirmed against official sources "
    "by a qualified person."
)

_LINE_ITEMS = (
    "line_no",
    "description",
    "hs_code_jp",
    "quantity",
    "quantity_unit",
    "net_weight_kg",
    "amount",
)


def build_declaration_draft(shipment: dict[str, Any], draft_number: str) -> dict[str, Any]:
    """検証に合格した shipment から、declaration_draft の中身を作る。"""
    parties = shipment["parties"]
    transport = shipment["transport"]
    terms = shipment["trade_terms"]

    unverified = [
        f"lines[{index}].hs_code_jp"
        for index, line in enumerate(shipment["lines"])
        if line["hs_code_jp"] is None
    ]
    if transport["etd"] is None:
        unverified.append("etd")

    return {
        "shipment_id": shipment["shipment_id"],
        "draft_number": draft_number,
        "mock": True,
        "exporter": dict(parties["exporter"] or parties["shipper"]),
        "consignee": dict(parties["consignee"]),
        "port_of_loading": transport["port_of_loading"],
        "port_of_discharge": transport["port_of_discharge"],
        "etd": transport["etd"],
        "incoterms": terms["incoterms"],
        "currency": terms["currency"],
        "invoice_amount": shipment["totals"]["amount"],
        "lines": [{key: line[key] for key in _LINE_ITEMS} for line in shipment["lines"]],
        "unverified": unverified,
        "note": MOCK_NOTE,
    }
