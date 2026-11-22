"""見本（samples/）を作り直すための道具。データはすべて架空。

使い方（PowerShell）:
    uv run python scripts\\make_samples.py

コンテナ番号の検査数字と合計はここで計算するので、手で書き写す間違いが入らない。
期待結果（.expected.json）は検証の結果から作らず、ここに直接書いてある。
"""

from __future__ import annotations

import copy
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trade_agent_profile import iso6346  # noqa: E402
from trade_agent_profile.demo import run_demo  # noqa: E402
from trade_agent_profile.profile import MESSAGE_TYPES  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))

from make_conformance import conformance_cases  # noqa: E402

VERSION = "0.1.0"
Json = dict[str, Any]

# 架空の当事者（名前に Sample / Example / Demo を入れて、実在の会社と区別する）
SELLER_A = ("Sample Metal Recycling K.K.", "1-1 Sample, Yokohama", "JP")
SELLER_B = ("Example Nonferrous K.K.", "2-2 Example, Nagoya", "JP")
SELLER_C = ("Demo Resource Recovery Co., Ltd.", "3-3 Demo, Osaka", "JP")
BUYER_A = ("Sample Trading (Shanghai) Co., Ltd.", "1 Sample Rd, Shanghai", "CN")
BUYER_B = ("Example Renewable Materials (Ningbo) Co., Ltd.", "8 Example Rd, Ningbo", "CN")
BUYER_C = ("Demo Metal Industry (Tianjin) Co., Ltd.", "5 Demo Ave, Tianjin", "CN")


def cn(serial: int) -> str:
    """架空のコンテナ番号。所有者コードは指示書の例と同じ CSQU に固定する。"""
    body = f"CSQU{serial:06d}"
    return f"{body}{iso6346.check_digit(body)}"


def dec(value: str | Decimal, places: int) -> str:
    return f"{Decimal(value):.{places}f}"


def kg(value: str | None) -> str | None:
    return None if value is None else dec(value, 3)


def party(spec: tuple[str, str, str]) -> Json:
    name, address, country = spec
    return {"name": name, "address": address, "country": country}


def container(serial: int, iso_type: str, seals: list[str], gross: str | None) -> Json:
    return {
        "number": cn(serial),
        "iso_type": iso_type,
        "seals": list(seals),
        "gross_weight_kg": kg(gross),
    }


def line(
    no: int,
    description: str,
    quantity: str,
    unit: str,
    net: str | None,
    gross: str | None,
    packages: int | None,
    package_type: str | None,
    unit_price: str,
    serial: int | None = None,
) -> Json:
    amount = Decimal(quantity) * Decimal(unit_price)
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError(f"金額が小数2桁に収まりません（明細 {no}）")
    return {
        "line_no": no,
        "description": description,
        "hs_code_jp": None,  # 品目番号は、出典で確かめるまで null にしておく
        "hs_code_dest": None,
        "origin_country": "JP",
        "quantity": dec(quantity, 3),
        "quantity_unit": unit,
        "net_weight_kg": kg(net),
        "gross_weight_kg": kg(gross),
        "packages": packages,
        "package_type": package_type,
        "unit_price": unit_price,
        "amount": dec(amount, 2),
        "container_number": None if serial is None else cn(serial),
    }


def totals(lines: list[Json]) -> Json:
    def total(key: str) -> str | None:
        values = [item[key] for item in lines]
        if any(value is None for value in values):
            return None
        return dec(sum((Decimal(value) for value in values), Decimal(0)), 3)

    counts = [item["packages"] for item in lines]
    return {
        "amount": dec(sum((Decimal(item["amount"]) for item in lines), Decimal(0)), 2),
        "net_weight_kg": total("net_weight_kg"),
        "gross_weight_kg": total("gross_weight_kg"),
        "packages": None if any(count is None for count in counts) else sum(counts),
    }


def field(
    value: Any,
    page: int | None = 1,
    bbox: list[float] | None = None,
    by: str = "human",
    confidence: float | None = None,
) -> Json:
    return {
        "value": value,
        "page": page,
        "bbox": bbox,
        "extracted_by": by,
        "confidence": confidence,
    }


def doc(
    doc_type: str,
    number: str,
    issue_date: str | None,
    fields: Json | None = None,
    file_ext: str | None = "pdf",
) -> Json:
    return {
        "doc_type": doc_type,
        "doc_number": number,
        "issue_date": issue_date,
        "file": None if file_ext is None else f"samples/docs/{number}.{file_ext}",
        "sha256": None,
        "fields": fields or {},
    }


def event(kind: str, at: str, by: str = "human", note: str | None = None) -> Json:
    return {"type": kind, "at": at, "by": by, "note": note}


def terms(incoterms: str, place: str, currency: str, payment: str | None) -> Json:
    return {
        "incoterms": incoterms,
        "incoterms_version": "2020",
        "place": place,
        "currency": currency,
        "payment_terms": payment,
    }


def transport(
    mode: str, loading: str, discharge: str, etd: str | None, eta: str | None, boxes: list[Json]
) -> Json:
    return {
        "mode": mode,
        "port_of_loading": loading,
        "port_of_discharge": discharge,
        "etd": etd,
        "eta": eta,
        "containers": boxes,
    }


def shipment(
    number: int,
    status: str,
    seller: tuple[str, str, str],
    buyer: tuple[str, str, str],
    trade_terms: Json,
    transport_: Json,
    lines: list[Json],
    documents: list[Json],
    events: list[Json],
    ext: Json | None = None,
) -> Json:
    return {
        "contract_version": VERSION,
        "shipment_id": f"SHP-2026-{number:04d}",
        "direction": "export",
        "status": status,
        "parties": {
            "shipper": party(seller),
            "exporter": party(seller),
            "consignee": party(buyer),
        },
        "trade_terms": trade_terms,
        "transport": transport_,
        "lines": lines,
        "totals": totals(lines),
        "documents": documents,
        "events": events,
        "ext": ext or {},
    }


def v01() -> Json:
    """指示書 第13節の例そのもの。"""
    return shipment(
        1,
        "draft",
        SELLER_A,
        BUYER_A,
        terms("FOB", "JPYOK", "USD", "T/T in advance"),
        transport(
            "sea",
            "JPYOK",
            "CNSHA",
            "2026-12-10",
            "2026-12-14",
            [container(305438, "22G1", ["SL000001"], "18250")],
        ),
        [
            line(
                1,
                "Aluminium scrap (sample)",
                "18000",
                "KGM",
                "18000",
                "18250",
                18,
                "BG",
                "1.25",
                305438,
            )
        ],
        [
            doc(
                "commercial_invoice",
                "INV-0001",
                "2026-12-01",
                {"totals.amount": field("22500.00", 1, [400.0, 610.5, 520.0, 624.0], "ai", 0.93)},
            )
        ],
        [event("created", "2026-12-01T09:00:00+09:00")],
    )


def v02() -> Json:
    return shipment(
        2,
        "checked",
        SELLER_B,
        BUYER_B,
        terms("CFR", "CNNGB", "USD", "L/C at sight"),
        transport(
            "sea",
            "JPNGO",
            "CNNGB",
            "2026-12-12",
            "2026-12-17",
            [
                container(305439, "22G1", ["SL000002"], "20350"),
                container(305440, "22G1", ["SL000003"], "19870"),
            ],
        ),
        [
            line(
                1,
                "Copper scrap (sample)",
                "20000",
                "KGM",
                "20000",
                "20350",
                20,
                "BG",
                "8.40",
                305439,
            ),
            line(
                2,
                "Brass scrap (sample)",
                "19500",
                "KGM",
                "19500",
                "19870",
                26,
                "BG",
                "5.10",
                305440,
            ),
        ],
        [
            doc(
                "commercial_invoice",
                "INV-0002",
                "2026-12-03",
                {"totals.amount": field("267450.00")},
            ),
            doc(
                "packing_list",
                "PL-0002",
                "2026-12-03",
                {
                    "totals.gross_weight_kg": field("40220.000", by="rule"),
                    "totals.packages": field(46, by="rule"),
                },
            ),
        ],
        [
            event("created", "2026-12-02T10:00:00+09:00"),
            event(
                "checked",
                "2026-12-04T15:30:00+09:00",
                "rule",
                "Invoice and packing list agree with the shipment data.",
            ),
        ],
    )


def v03() -> Json:
    baled = "Aluminium alloy scrap, baled (sample)"
    return shipment(
        3,
        "submitted",
        SELLER_C,
        BUYER_C,
        terms("CIF", "CNTXG", "USD", "T/T 30% in advance, 70% against copy of B/L"),
        transport(
            "sea",
            "JPOSA",
            "CNTXG",
            "2026-12-15",
            "2026-12-21",
            [
                container(305441, "45G1", ["SL000004"], "24120"),
                container(305442, "45G1", ["SL000005"], "23620"),
                container(305443, "45G1", ["SL000006"], "25150"),
            ],
        ),
        [
            line(1, baled, "24000", "KGM", "24000", "24120", 24, "BL", "1.32", 305441),
            line(2, baled, "23500", "KGM", "23500", "23620", 24, "BL", "1.32", 305442),
            line(
                3,
                "Stainless steel scrap (sample)",
                "25000",
                "KGM",
                "25000",
                "25150",
                30,
                "BL",
                "0.95",
                305443,
            ),
        ],
        [
            doc(
                "commercial_invoice",
                "INV-0003",
                "2026-12-10",
                {
                    "totals.amount": field("86450.00", 1, [402.5, 598.0, 518.0, 612.0], "ai", 0.97),
                    "trade_terms.incoterms": field(
                        "CIF", 1, [60.0, 180.0, 96.0, 194.0], "ai", 0.99
                    ),
                },
            ),
            doc(
                "packing_list",
                "PL-0003",
                "2026-12-10",
                {
                    "totals.packages": field(78, by="rule"),
                    "totals.net_weight_kg": field("72500.000", by="rule"),
                },
            ),
            doc(
                "bill_of_lading",
                "BL-0003",
                "2026-12-15",
                {
                    "transport.containers[0].number": field(cn(305441)),
                    "transport.port_of_loading": field("JPOSA"),
                },
            ),
            doc("insurance_certificate", "INS-0003", "2026-12-12"),
        ],
        [
            event("created", "2026-12-08T10:00:00+09:00"),
            event(
                "checked", "2026-12-11T14:00:00+09:00", "rule", "All totals agree with the lines."
            ),
            event("submitted", "2026-12-12T09:30:00+09:00"),
        ],
    )


def v04() -> Json:
    return shipment(
        4,
        "draft",
        SELLER_A,
        BUYER_A,
        terms("FCA", "JPTYO", "USD", None),
        transport("sea", "JPTYO", "CNSHA", None, None, [container(305444, "42G1", [], None)]),
        [
            line(
                1,
                "Aluminium scrap (sample)",
                "4.5",
                "TNE",
                "4500",
                "4560",
                5,
                "BG",
                "1250.00",
                305444,
            ),
            line(
                2, "Copper scrap (sample)", "5", "TNE", "5000", "5060", 5, "BG", "8400.00", 305444
            ),
            line(
                3, "Brass scrap (sample)", "4.2", "TNE", "4200", "4255", 6, "BG", "5100.00", 305444
            ),
            line(
                4, "Zinc scrap (sample)", "3.8", "TNE", "3800", "3850", 4, "DR", "2100.00", 305444
            ),
            line(
                5,
                "Stainless steel scrap (sample)",
                "5.5",
                "TNE",
                "5500",
                "5570",
                6,
                "BX",
                "950.00",
                305444,
            ),
        ],
        [],
        [event("created", "2026-12-05T13:00:00+09:00")],
    )


def v05() -> Json:
    return shipment(
        5,
        "approved",
        SELLER_C,
        BUYER_B,
        terms("FOB", "JPOSA", "JPY", "T/T within 5 days after B/L date"),
        transport("sea", "JPOSA", "CNTAO", "2026-12-20", "2026-12-24", []),
        [
            line(
                1,
                "Steel scrap, heavy melting, in bulk (sample)",
                "3000",
                "TNE",
                "3000000",
                "3000000",
                None,
                None,
                "52000.00",
            )
        ],
        [
            doc(
                "commercial_invoice",
                "INV-0005",
                "2026-12-16",
                {"totals.amount": field("156000000.00")},
            ),
            doc("bill_of_lading", "BL-0005", "2026-12-20", {"transport.etd": field("2026-12-20")}),
            doc(
                "weight_certificate",
                "WC-0005",
                "2026-12-19",
                {"totals.net_weight_kg": field("3000000.000")},
            ),
            doc("export_declaration", "ED-0005", "2026-12-17"),
            doc("export_permit", "EP-0005", "2026-12-18"),
        ],
        [
            event("created", "2026-12-14T09:00:00+09:00"),
            event("checked", "2026-12-16T11:00:00+09:00", "rule"),
            event("submitted", "2026-12-17T10:00:00+09:00"),
            event("approved", "2026-12-18T16:45:00+09:00", "human", "Export permit received."),
        ],
    )


def v06() -> Json:
    return shipment(
        6,
        "checked",
        SELLER_B,
        BUYER_A,
        terms("CIP", "CNSHA", "USD", "T/T in advance"),
        transport("air", "JPNRT", "CNSHA", "2026-12-08", "2026-12-08", []),
        [
            line(
                1,
                "Copper alloy scrap, assay lot (sample)",
                "120",
                "KGM",
                "120",
                "132.5",
                4,
                "BX",
                "9.80",
            )
        ],
        [
            doc(
                "commercial_invoice",
                "INV-0006",
                "2026-12-05",
                {"lines[0].amount": field("1176.00", 1, [410.0, 420.0, 505.0, 434.0], "ai", 0.88)},
            ),
            doc("packing_list", "PL-0006", "2026-12-05", {"lines[0].packages": field(4)}),
            doc("other", "AWB-0006", "2026-12-08"),
        ],
        [
            event("created", "2026-12-04T11:00:00+09:00"),
            event(
                "checked",
                "2026-12-06T16:20:00+09:00",
                "ai",
                "Document values match the shipment data.",
            ),
        ],
    )


def v07() -> Json:
    return shipment(
        7,
        "draft",
        SELLER_A,
        BUYER_C,
        terms("EXW", "JPTYO", "CNY", None),
        transport("air", "JPNRT", "CNSHA", None, None, []),
        [
            line(1, "Tin scrap (sample)", "300", "KGM", "300", "318", 6, "BX", "152.00"),
            line(2, "Nickel alloy scrap (sample)", "250", "KGM", "250", "266", 5, "BX", "91.00"),
        ],
        [doc("packing_list", "PL-0007", None, file_ext=None)],
        [event("created", "2026-12-09T15:00:00+09:00")],
    )


def v08() -> Json:
    return shipment(
        8,
        "submitted",
        SELLER_B,
        BUYER_C,
        terms("DAP", "CNWUH", "USD", "L/C 60 days after B/L date"),
        transport(
            "multimodal",
            "JPYOK",
            "CNSHA",
            "2026-12-18",
            "2026-12-22",
            [
                container(305445, "22G1", ["SL000007"], "20240"),
                container(305446, "22G1", ["SL000008"], "20250"),
            ],
        ),
        [
            line(
                1,
                "Aluminium scrap (sample)",
                "12000",
                "KGM",
                "12000",
                "12150",
                12,
                "BG",
                "1.28",
                305445,
            ),
            line(
                2,
                "Copper wire scrap (sample)",
                "8000",
                "KGM",
                "8000",
                "8090",
                8,
                "BG",
                "8.65",
                305445,
            ),
            line(
                3,
                "Brass scrap (sample)",
                "11000",
                "KGM",
                "11000",
                "11140",
                11,
                "BG",
                "5.05",
                305446,
            ),
            line(4, "Zinc scrap (sample)", "9000", "KGM", "9000", "9110", 9, "DR", "2.15", 305446),
        ],
        [
            doc(
                "commercial_invoice",
                "INV-0008",
                "2026-12-12",
                {"totals.amount": field("159460.00", 1, [398.0, 640.0, 520.0, 654.0], "ai", 0.94)},
            ),
            doc(
                "packing_list",
                "PL-0008",
                "2026-12-12",
                {"totals.gross_weight_kg": field("40490.000", by="rule")},
            ),
            doc(
                "sea_waybill",
                "SWB-0008",
                "2026-12-18",
                {"transport.port_of_discharge": field("CNSHA")},
            ),
            doc(
                "certificate_of_origin",
                "CO-0008",
                "2026-12-13",
                {"lines[0].origin_country": field("JP")},
            ),
        ],
        [
            event("created", "2026-12-10T09:30:00+09:00"),
            event("checked", "2026-12-13T13:00:00+09:00", "rule"),
            event("submitted", "2026-12-14T10:00:00+09:00"),
        ],
    )


def v09() -> Json:
    """書類の値が正本と違い、その食い違いを events に記録してある例。"""
    return shipment(
        9,
        "checked",
        SELLER_C,
        BUYER_A,
        terms("CIF", "CNXMN", "USD", "T/T in advance"),
        transport(
            "sea",
            "JPUKB",
            "CNXMN",
            "2026-12-11",
            "2026-12-16",
            [container(305447, "22G1", ["SL000009"], "21840")],
        ),
        [
            line(
                1,
                "Aluminium scrap (sample)",
                "10000",
                "KGM",
                "10000",
                "10120",
                10,
                "BG",
                "1.30",
                305447,
            ),
            line(
                2,
                "Stainless steel scrap (sample)",
                "11500",
                "KGM",
                "11500",
                "11720",
                12,
                "BX",
                "0.98",
                305447,
            ),
        ],
        [
            doc(
                "commercial_invoice",
                "INV-0009",
                "2026-12-07",
                {"totals.amount": field("24270.00", 1, [400.0, 600.0, 520.0, 614.0], "ai", 0.95)},
            ),
            doc(
                "packing_list",
                "PL-0009",
                "2026-12-07",
                {"totals.gross_weight_kg": field("21480.000")},
            ),
        ],
        [
            event("created", "2026-12-06T09:00:00+09:00"),
            event(
                "discrepancy_noted",
                "2026-12-08T10:15:00+09:00",
                "rule",
                "PL-0009 shows a gross weight of 21480.000 kg; the authoritative value is "
                "21840.000 kg. The shipper was asked to reissue the packing list.",
            ),
            event("checked", "2026-12-08T10:30:00+09:00"),
        ],
    )


def v10() -> Json:
    return shipment(
        10,
        "approved",
        SELLER_A,
        BUYER_C,
        terms("CPT", "CNDLC", "USD", "T/T 20% in advance, balance against documents"),
        transport(
            "multimodal",
            "JPTYO",
            "CNDLC",
            "2026-12-22",
            "2026-12-27",
            [
                container(305448, "45G1", ["SL000010"], "22130"),
                container(305449, "22G1", ["SL000011"], "19680"),
                container(305450, "22G1", ["SL000012", "SL000013"], "21700"),
            ],
        ),
        [
            line(
                1,
                "Aluminium alloy scrap, baled (sample)",
                "22000",
                "KGM",
                "22000",
                "22130",
                22,
                "BL",
                "1.35",
                305448,
            ),
            line(
                2, "Copper scrap (sample)", "9000", "KGM", "9000", "9080", 9, "BG", "8.50", 305449
            ),
            line(
                3,
                "Brass scrap (sample)",
                "10500",
                "KGM",
                "10500",
                "10600",
                10,
                "BG",
                "5.20",
                305449,
            ),
            line(
                4,
                "Stainless steel scrap (sample)",
                "12000",
                "KGM",
                "12000",
                "12110",
                12,
                "BX",
                "0.96",
                305450,
            ),
            line(5, "Zinc scrap (sample)", "9500", "KGM", "9500", "9590", 10, "DR", "2.20", 305450),
        ],
        [
            doc(
                "commercial_invoice",
                "INV-0010",
                "2026-12-17",
                {
                    "totals.amount": field(
                        "193220.00", 1, [401.0, 655.0, 522.0, 669.0], "ai", 0.96
                    ),
                    "trade_terms.incoterms": field(
                        "CPT", 1, [58.0, 176.0, 94.0, 190.0], "ai", 0.91
                    ),
                    "parties.consignee.name": field("Demo Metal Industry (Tianjin) Co., Ltd."),
                },
            ),
            doc(
                "packing_list",
                "PL-0010",
                "2026-12-17",
                {
                    "totals.packages": field(63, by="rule"),
                    "totals.net_weight_kg": field("63000.000", by="rule"),
                },
            ),
            doc(
                "bill_of_lading",
                "BL-0010",
                "2026-12-22",
                {
                    "transport.containers[2].number": field(cn(305450)),
                    "transport.etd": field("2026-12-22"),
                },
            ),
            doc(
                "certificate_of_origin",
                "CO-0010",
                "2026-12-18",
                {"lines[0].origin_country": field("JP")},
            ),
            doc("export_declaration", "ED-0010", "2026-12-19"),
            doc("export_permit", "EP-0010", "2026-12-20"),
            doc("photo", "PH-0010", "2026-12-20", file_ext="jpg"),
        ],
        [
            event("created", "2026-12-15T09:00:00+09:00"),
            event("checked", "2026-12-18T15:00:00+09:00", "rule"),
            event("submitted", "2026-12-19T10:00:00+09:00"),
            event("approved", "2026-12-20T17:00:00+09:00", "human", "Export permit received."),
        ],
        {"example-project": {"internal_ref": "X-0010", "tags": ["demo", "sample"]}},
    )


def demo_shipment() -> Json:
    """台本デモで使う船積み。書類の値は正本とそろっている。"""
    return shipment(
        100,
        "checked",
        SELLER_C,
        BUYER_A,
        terms("CIF", "CNXMN", "USD", "T/T in advance"),
        transport(
            "sea",
            "JPUKB",
            "CNXMN",
            "2026-12-11",
            "2026-12-16",
            [container(305451, "22G1", ["SL000014"], "21840")],
        ),
        [
            line(
                1,
                "Aluminium scrap (sample)",
                "10000",
                "KGM",
                "10000",
                "10120",
                10,
                "BG",
                "1.30",
                305451,
            ),
            line(
                2,
                "Stainless steel scrap (sample)",
                "11500",
                "KGM",
                "11500",
                "11720",
                12,
                "BX",
                "0.98",
                305451,
            ),
        ],
        [
            doc(
                "commercial_invoice",
                "INV-0100",
                "2026-12-05",
                {"totals.amount": field("24270.00", 1, [400.0, 600.0, 520.0, 614.0], "ai", 0.95)},
            ),
            doc(
                "packing_list",
                "PL-0100",
                "2026-12-05",
                {
                    "totals.gross_weight_kg": field("21840.000"),
                    "totals.packages": field(22),
                },
            ),
        ],
        [
            event("created", "2026-11-30T15:00:00+09:00"),
            event("checked", "2026-12-06T11:00:00+09:00", "rule"),
        ],
    )


def message_samples(demo: Json) -> dict[str, Json]:
    """台本デモに出てくるメッセージから、種類ごとに最初の1件を見本にする。"""
    first: dict[str, Json] = {}
    for entry in run_demo(demo).entries:
        if entry.envelope is not None:
            first.setdefault(entry.envelope["message_type"], entry.envelope)
    return {f"{number:02d}_{kind}": first[kind] for number, kind in enumerate(MESSAGE_TYPES, 1)}


VALID = {
    "01_sea_fob_1c_1l": v01,
    "02_sea_cfr_2c_2l": v02,
    "03_sea_cif_3c_3l": v03,
    "04_sea_fca_1c_5l": v04,
    "05_sea_fob_bulk_0c_1l": v05,
    "06_air_cip_0c_1l": v06,
    "07_air_exw_0c_2l": v07,
    "08_multimodal_dap_2c_4l": v08,
    "09_sea_cif_1c_2l_discrepancy_noted": v09,
    "10_multimodal_cpt_3c_5l": v10,
}


def invalid_cases() -> list[tuple[str, Json, str, str]]:
    """誤り例。指示書の例（v01）を土台に、1件につき1種類だけ誤りを入れる。"""

    def base(number: int) -> Json:
        data = copy.deepcopy(v01())
        data["shipment_id"] = f"SHP-2026-{9000 + number:04d}"
        return data

    cases: list[tuple[str, Json, str, str]] = []

    data = base(1)  # 必須項目の欠落
    del data["parties"]["consignee"]
    cases.append(("01_required_missing", data, "REQUIRED_MISSING", "parties.consignee"))

    data = base(2)  # 型の違い（整数であるべき個数が文字列）
    data["lines"][0]["packages"] = "18"
    cases.append(("02_type_mismatch", data, "TYPE_MISMATCH", "lines[0].packages"))

    data = base(3)  # コードの形式違反（UN/LOCODE は5文字）
    data["transport"]["port_of_discharge"] = "SHA"
    cases.append(("03_code_format", data, "FORMAT_INVALID", "transport.port_of_discharge"))

    data = base(4)  # コンテナ番号の検査数字（正しくは 3）
    data["transport"]["containers"][0]["number"] = "CSQU3054384"
    data["lines"][0]["container_number"] = "CSQU3054384"
    cases.append(
        (
            "04_container_check_digit",
            data,
            "CONTAINER_CHECK_DIGIT",
            "transport.containers[0].number",
        )
    )

    data = base(5)  # 明細合計と総額の不一致（明細は 22500.00）
    data["totals"]["amount"] = "22050.00"
    data["documents"][0]["fields"]["totals.amount"]["value"] = "22050.00"
    cases.append(("05_total_mismatch", data, "TOTAL_MISMATCH", "totals.amount"))

    data = base(6)  # 日付の前後（到着が出発より前）
    data["transport"]["etd"] = "2026-12-14"
    data["transport"]["eta"] = "2026-12-10"
    cases.append(("06_date_order", data, "DATE_ORDER", "transport.eta"))

    data = base(7)  # 列挙値の外
    data["status"] = "shipped"
    cases.append(("07_enum_out_of_range", data, "ENUM_INVALID", "status"))

    data = base(8)  # ext の置き場所の違反（独自の項目を最上位に置いた）
    data["inspection_memo"] = {"checked_by": "yard staff", "result": "ok"}
    cases.append(("08_ext_misplaced", data, "UNKNOWN_FIELD", "inspection_memo"))

    data = base(9)  # 版の不一致
    data["contract_version"] = "0.2.0"
    cases.append(("09_version_mismatch", data, "VERSION_UNSUPPORTED", "contract_version"))

    data = base(10)  # 書類と正本の食い違いの記載漏れ（正本は 22500.00）
    data["documents"][0]["fields"]["totals.amount"]["value"] = "22000.00"
    cases.append(
        (
            "10_discrepancy_not_recorded",
            data,
            "DISCREPANCY_NOT_RECORDED",
            'documents[0].fields["totals.amount"]',
        )
    )
    return cases


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def build_all() -> dict[str, str]:
    """作るファイルの一覧（場所 → 中身）。"""
    files: dict[str, str] = {}
    for name, builder in VALID.items():
        files[f"samples/valid/{name}.json"] = dumps(builder())
    for name, data, code, path in invalid_cases():
        files[f"samples/invalid/{name}.json"] = dumps(data)
        expected = {"valid": False, "errors": [{"code": code, "path": path}]}
        files[f"samples/invalid/{name}.expected.json"] = dumps(expected)
    demo = demo_shipment()
    files["src/trade_agent_profile/data/demo_shipment.json"] = dumps(demo)
    for name, envelope in message_samples(demo).items():
        files[f"samples/messages/{name}.json"] = dumps(envelope)
    for name, case in conformance_cases(demo).items():
        files[f"conformance/cases/{name}.json"] = dumps(case)
    return files


def main() -> int:
    files = build_all()
    for relative, text in files.items():
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    print(f"見本を書き出しました: {len(files)} ファイル")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
