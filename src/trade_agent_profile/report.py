"""台本デモの記録を、時系列で読める HTML にする。

値の出どころ（規則による計算・未確認）を、値の横に表示する。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import i18n
from .agents import BrokerAgent
from .demo import EXTRA_SCENES, MAIN_SCENES, Entry

_TEMPLATES = Path(__file__).parent / "templates"
Fact = dict[str, Any]


def _fact(label: str, value: Any, basis: str | None = None) -> Fact:
    return {"label": label, "value": str(value), "basis": basis}


def _shipment_facts(shipment: dict[str, Any], f: dict[str, str]) -> list[Fact]:
    transport = shipment["transport"]
    route = (
        f"{transport['port_of_loading']} → {transport['port_of_discharge']}（{transport['mode']}）"
    )
    cargo = f["cargo_text"].format(
        lines=len(shipment["lines"]),
        containers=len(transport["containers"]),
        gross=shipment["totals"]["gross_weight_kg"],
    )
    return [
        _fact(f["shipment_id"], shipment["shipment_id"]),
        _fact(f["route"], route),
        _fact(f["cargo"], cargo),
    ]


def _facts(envelope: dict[str, Any], f: dict[str, str], lang: str) -> list[Fact]:
    """メッセージの要点を、人が読める行にする。"""
    kind = envelope["message_type"]
    p = envelope["payload"]
    facts: list[Fact] = []

    if kind in ("quote_request", "booking_request", "document_submission") and isinstance(
        p.get("shipment"), dict
    ):
        facts += _shipment_facts(p["shipment"], f)
    if kind == "quote_request" and p.get("reply_by"):
        facts.append(_fact(f["reply_by"], p["reply_by"]))
    elif kind == "quote":
        facts.append(_fact(f["quote_number"], p["quote_number"]))
        facts += [
            _fact(f["charge"], f"{c['name']}: {c['amount']} {p['currency']}", "rule")
            for c in p["charges"]
        ]
        facts.append(_fact(f["total"], f"{p['total']} {p['currency']}", "rule"))
        facts.append(_fact(f["valid_until"], p["valid_until"], "rule"))
    elif kind == "booking_request":
        facts.append(_fact(f["quote_number"], p["quote_number"]))
    elif kind == "booking_confirmation":
        facts.append(_fact(f["booking_number"], p["booking_number"]))
        facts.append(_fact(f["etd"], p["etd"], "rule"))
        facts.append(_fact(f["eta"], p["eta"], "rule"))
        if p["cargo_cutoff_at"]:
            facts.append(_fact(f["cargo_cutoff_at"], p["cargo_cutoff_at"], "rule"))
    elif kind == "document_submission" and isinstance(p.get("shipment"), dict):
        numbers = [d["doc_number"] or d["doc_type"] for d in p["shipment"]["documents"]]
        facts.append(_fact(f["documents"], ", ".join(numbers)))
    elif kind == "discrepancy_notice":
        for item in p["discrepancies"]:
            text = f["discrepancy_text"].format(
                document=item["doc_number"] or item["doc_type"],
                path=item["path"],
                document_value=item["document_value"],
                authoritative_value=item["authoritative_value"],
            )
            facts.append(_fact(f["discrepancy"], text, "rule"))
    elif kind == "declaration_draft":
        route = f"{p['port_of_loading']} → {p['port_of_discharge']}"
        facts.append(_fact(f["draft_number"], p["draft_number"]))
        facts.append(_fact(f["mock"], f["mock_text"]))
        facts.append(_fact(f["exporter"], p["exporter"]["name"], "rule"))
        facts.append(_fact(f["consignee"], p["consignee"]["name"], "rule"))
        facts.append(_fact(f["route"], route, "rule"))
        if p["etd"]:
            facts.append(_fact(f["etd"], p["etd"], "rule"))
        facts.append(_fact(f["incoterms"], p["incoterms"], "rule"))
        facts.append(_fact(f["invoice_amount"], f"{p['invoice_amount']} {p['currency']}", "rule"))
        for line in p["lines"]:
            text = f["line_text"].format(
                description=line["description"],
                quantity=line["quantity"],
                unit=line["quantity_unit"],
                amount=line["amount"],
            )
            facts.append(_fact(f["line"].format(no=line["line_no"]), text, "rule"))
            label = f["hs_code_jp"].format(no=line["line_no"])
            if line["hs_code_jp"] is None:
                facts.append(_fact(label, f["unverified_value"], "unverified"))
            else:
                facts.append(_fact(label, line["hs_code_jp"], "rule"))
    elif kind in ("approval", "rejection"):
        if p["shipment_id"]:
            facts.append(_fact(f["shipment_id"], p["shipment_id"]))
        if kind == "rejection":
            facts.append(_fact(f["reason"], p["reason"]))
    elif kind == "error":
        facts.append(_fact(f["error_code"], p["code"]))
        facts.append(_fact(f["error_text"], p["text"][lang]))
        facts += [_fact(f["issue"], f"[{i['code']}] {i['path']}") for i in p["issues"]]

    if p.get("note"):
        facts.append(_fact(f["note"], p["note"]))
    return facts


def _view(number: int, entry: Entry, t: dict[str, Any], names: dict[str, str], lang: str) -> dict:
    receiver = "broker" if entry.sender == "shipper" else "shipper"
    envelope = entry.envelope
    return {
        "number": number,
        "time": entry.at[:16].replace("T", " "),
        "side": entry.sender,
        "sender": names[entry.sender],
        "receiver": names[receiver],
        "type": envelope["message_type"] if envelope else None,
        "type_name": t["types"][envelope["message_type"]] if envelope else t["state_only"],
        "state": entry.state,
        "state_name": t["states"].get(entry.state, entry.state) if entry.state else None,
        "task": entry.task_id[:8] if entry.task_id else None,
        "carrier": t["carrier"][entry.kind],
        "duplicate": entry.duplicate,
        "facts": _facts(envelope, t["facts"], lang) if envelope else [],
        "json": json.dumps(envelope, ensure_ascii=False, indent=2) if envelope else None,
    }


def _card_lines(cards: list[dict[str, Any]], t: dict[str, Any]) -> list[str]:
    """AgentCard の要点（card_summary の結果）を、1件1行の文にする。"""
    lines = []
    for card in cards:
        interface = card["interfaces"][0] if card["interfaces"] else {}
        lines.append(
            t["card_line"].format(
                name=card["name"],
                declared=t["yes"] if card["declares_profile"] else t["no"],
                binding=interface.get("binding", "-"),
                version=interface.get("version", "-"),
                accepts=", ".join(card["accepts"]) or t["none"],
            )
        )
    return lines


def render(
    entries: list[Entry],
    lang: str = "ja",
    *,
    wire: str | None = None,
    cards: list[dict[str, Any]] | None = None,
) -> str:
    """記録を1枚の HTML にする。画像や外部のファイルは使わない。

    wire に "a2a" を渡すと、実際に A2A で通信した記録として説明の文を切り替える。
    cards には、AgentCard の要点（a2a_agent.card_summary の結果）を渡す。
    """
    cat = i18n.catalog(lang)
    t = cat["report"]
    suffix = f"_{wire}" if wire else ""
    shipper_name = next(e.envelope["sender"]["name"] for e in entries if e.sender == "shipper")
    names = {
        "shipper": f"{t['party']['shipper']}（{shipper_name}）",
        "broker": f"{t['party']['broker']}（{BrokerAgent.NAME}）",
    }
    views = {index: _view(index, entry, t, names, lang) for index, entry in enumerate(entries, 1)}

    def scenes(keys: tuple[str, ...]) -> list[dict[str, Any]]:
        return [
            {
                "title": t["scenes"][key]["title"],
                "text": t["scenes"][key]["text"],
                "entries": [views[i] for i, e in enumerate(entries, 1) if e.scene == key],
            }
            for key in keys
        ]

    environment = Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template("demo.html.j2")
    return template.render(
        lang=lang,
        t=t,
        ui=cat["ui"],
        names=names,
        transport_note=t[f"transport_note{suffix}"],
        footer=t[f"footer{suffix}"],
        cards=_card_lines(cards or [], t),
        main=scenes(MAIN_SCENES),
        extra=scenes(EXTRA_SCENES),
    )
