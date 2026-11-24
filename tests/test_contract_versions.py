"""契約の版（0.1.0 と 0.1.1）ごとの検証。

- 0.1.1 のデータでは、足した6つの項目を調べる。
- 0.1.0 のデータは、0.1.0 だけだったころのスキーマとまったく同じ結果になる。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from conftest import SAMPLES, SAMPLES_V010, load_json
from jsonschema import Draft202012Validator
from test_validator import CASES, Change, delp, setp

from trade_agent_profile import (
    LATEST_CONTRACT_VERSION,
    SUPPORTED_CONTRACT_VERSIONS,
    find_discrepancies,
    i18n,
    load_schema,
    validate_shipment,
)
from trade_agent_profile.declaration import build_declaration_draft
from trade_agent_profile.messages import new_message, validate_message
from trade_agent_profile.profile import COMPLETED
from trade_agent_profile.reference import broker_receiver, new_uuid, now_text
from trade_agent_profile.validator import schema_issues, schema_validator

Data = dict[str, Any]
ORIGINAL = Path(__file__).parent / "data" / "shipment-0.1.0.original.schema.json"
PARTY = {"name": "Sample Notify Co., Ltd.", "address": None, "country": "CN"}
ADDED = [
    "parties.notify_parties",
    "trade_terms.freight_amount",
    "trade_terms.insurance_premium_amount",
    "transport.vessel_name",
    "transport.voyage_number",
    "transport.booking_number",
]


def pairs(data: Any) -> set[tuple[str, str]]:
    return {(issue.code, issue.path) for issue in validate_shipment(data).errors}


@pytest.fixture(scope="module")
def original() -> Draft202012Validator:
    """0.1.0 だけだったころのスキーマ（公開したものの控え）。"""
    return Draft202012Validator(json.loads(ORIGINAL.read_text(encoding="utf-8")))


def test_versions() -> None:
    assert SUPPORTED_CONTRACT_VERSIONS == ("0.1.0", "0.1.1")
    assert LATEST_CONTRACT_VERSION == "0.1.1"
    schema = load_schema()
    known = schema["allOf"][0]["then"]["properties"]["contract_version"]["enum"]
    assert tuple(known) == SUPPORTED_CONTRACT_VERSIONS  # スキーマと検証の一覧が同じ


# ---- 0.1.1 で足した項目 ----


@pytest.mark.parametrize("path", ADDED)
def test_added_items_cannot_be_left_out_in_v011(base: Data, path: str) -> None:
    """0.1.1 のデータでは、足した項目も省けない（分からなければ null か空の一覧）。"""
    delp(path)(base)
    assert pairs(base) == {("REQUIRED_MISSING", path)}


@pytest.mark.parametrize("path", ADDED)
def test_added_items_are_unknown_in_v010(base_v010: Data, path: str) -> None:
    """0.1.0 のデータに 0.1.1 の項目を書くと、その版にない項目として誤りになる。"""
    setp(path, [] if path.endswith("notify_parties") else None)(base_v010)
    assert pairs(base_v010) == {("UNKNOWN_FIELD", path)}


VALUES: list[tuple[str, list[Change], set[tuple[str, str]]]] = [
    ("通知先は3件まで", [setp("parties.notify_parties", [PARTY] * 3)], set()),
    (
        "通知先が4件",
        [setp("parties.notify_parties", [PARTY] * 4)],
        {("ARRAY_LENGTH", "parties.notify_parties")},
    ),
    (
        "通知先を null にはできない（いなければ空の一覧）",
        [setp("parties.notify_parties", None)],
        {("REQUIRED_NULL", "parties.notify_parties")},
    ),
    (
        "通知先を1件のオブジェクトで書いた",
        [setp("parties.notify_parties", PARTY)],
        {("TYPE_MISMATCH", "parties.notify_parties")},
    ),
    (
        "通知先の名称がない",
        [setp("parties.notify_parties", [{"address": None, "country": "CN"}])],
        {("REQUIRED_MISSING", "parties.notify_parties[0].name")},
    ),
    (
        "通知先の国の形式",
        [setp("parties.notify_parties", [{**PARTY, "country": "China"}])],
        {("FORMAT_INVALID", "parties.notify_parties[0].country")},
    ),
    (
        "通知先に決められていない項目",
        [setp("parties.notify_parties", [{**PARTY, "phone": "000"}])],
        {("UNKNOWN_FIELD", "parties.notify_parties[0].phone")},
    ),
    ("運賃の額", [setp("trade_terms.freight_amount", "1900.00")], set()),
    (
        "運賃の額が小数2桁でない",
        [setp("trade_terms.freight_amount", "1900")],
        {("FORMAT_INVALID", "trade_terms.freight_amount")},
    ),
    (
        "運賃の額を数値で書いた",
        [setp("trade_terms.freight_amount", 1900.0)],
        {("TYPE_MISMATCH", "trade_terms.freight_amount")},
    ),
    (
        "保険料の額が負",
        [setp("trade_terms.insurance_premium_amount", "-5.00")],
        {("FORMAT_INVALID", "trade_terms.insurance_premium_amount")},
    ),
    (
        "船名・航海番号・ブッキング番号",
        [
            setp("transport.vessel_name", "SAMPLE EXPRESS"),
            setp("transport.voyage_number", "0123W"),
            setp("transport.booking_number", "BKG-SAMPLE-0001"),
        ],
        set(),
    ),
    (
        "船名が空の文字列",
        [setp("transport.vessel_name", "")],
        {("EMPTY_VALUE", "transport.vessel_name")},
    ),
    (
        "ブッキング番号を数値で書いた",
        [setp("transport.booking_number", 12345)],
        {("TYPE_MISMATCH", "transport.booking_number")},
    ),
    (
        "似た名前（insurance_amount）は、決められた項目ではない",
        [setp("trade_terms.insurance_amount", "10.00")],
        {("UNKNOWN_FIELD", "trade_terms.insurance_amount")},
    ),
]


@pytest.mark.parametrize(
    ("changes", "expected"), [case[1:] for case in VALUES], ids=[case[0] for case in VALUES]
)
def test_added_items_are_checked(
    base: Data, changes: list[Change], expected: set[tuple[str, str]]
) -> None:
    for change in changes:
        change(base)
    result = validate_shipment(base)
    assert {(issue.code, issue.path) for issue in result.errors} == expected
    for issue in result.errors:  # 説明に、項目の名前（日本語と英語）が付く
        for lang in i18n.LANGS:
            if issue.code != "UNKNOWN_FIELD":  # 決められていない項目には、名前がない
                assert issue.label(lang), issue.path
            assert issue.why(lang) and issue.fix(lang)


def test_values_read_from_documents_can_point_to_the_added_items(base: Data) -> None:
    """書類から読み取った値（fields）で、足した項目を指せる。金額は数として比べる。"""
    base["trade_terms"]["freight_amount"] = "1900.00"
    base["transport"]["vessel_name"] = "SAMPLE EXPRESS"
    base["parties"]["notify_parties"] = [dict(PARTY)]
    entry = base["documents"][0]["fields"]["totals.amount"]
    fields = base["documents"][0]["fields"]
    fields["trade_terms.freight_amount"] = {**entry, "value": "1900.0"}  # 書き方が違うだけ
    fields["transport.vessel_name"] = {**entry, "value": "SAMPLE EXPRESS"}
    fields["parties.notify_parties[0].name"] = {**entry, "value": PARTY["name"]}
    assert pairs(base) == set()
    assert find_discrepancies(base) == []

    fields["trade_terms.freight_amount"]["value"] = "1800.00"  # 書類の値が正本と違う
    assert pairs(base) == {
        ("DISCREPANCY_NOT_RECORDED", 'documents[0].fields["trade_terms.freight_amount"]')
    }
    found = find_discrepancies(base)
    assert [(item["path"], item["document_value"]) for item in found] == [
        ("trade_terms.freight_amount", "1800.00")
    ]


def test_values_read_from_documents_cannot_point_to_added_items_in_v010(base_v010: Data) -> None:
    entry = base_v010["documents"][0]["fields"]["totals.amount"]
    base_v010["documents"][0]["fields"]["transport.vessel_name"] = {**entry, "value": "X"}
    assert pairs(base_v010) == {
        ("FIELD_PATH_INVALID", 'documents[0].fields["transport.vessel_name"]')
    }


# ---- 0.1.0 のデータは、今までと同じ結果になる ----


@pytest.mark.parametrize(
    ("changes", "expected"), [case[1:] for case in CASES], ids=[case[0] for case in CASES]
)
def test_v010_gives_the_same_result_as_before(
    base_v010: Data,
    original: Draft202012Validator,
    changes: list[Change],
    expected: set[tuple[str, str]],
) -> None:
    """test_validator.py の変更の一覧を、0.1.0 のデータにも当てる。

    結果が期待どおりで、スキーマの段の結果が、0.1.0 だけだったころのスキーマと同じこと。
    """
    for change in changes:
        change(base_v010)
    assert pairs(base_v010) == expected
    if base_v010.get("contract_version") == "0.1.0":
        now = schema_issues(base_v010, schema_validator())
        before = schema_issues(base_v010, original)
        assert [(i.code, i.path, i.params) for i in now] == [
            (i.code, i.path, i.params) for i in before
        ]


def _every_key(data: Any, prefix: str = "") -> list[str]:
    """データの中のすべての項目の場所（配列は先頭の要素だけ）。"""
    found: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if "." in key:  # fields のキー（道筋）は、ここでは扱わない
                continue
            path = f"{prefix}.{key}" if prefix else key
            found.append(path)
            if path != "ext":  # ext の中は、名前も中身も各プロジェクトのもの
                found += _every_key(value, path)
    elif isinstance(data, list) and data:
        found += _every_key(data[0], f"{prefix}[0]")
    return found


VERSIONED = ("parties", "trade_terms", "transport")  # 版によって形を選ぶ部分


def _mutations(data: Data) -> list[tuple[str, Data]]:
    """1か所ずつ変えた写し：項目を消す、null にする、型を変える、知らない項目を足す。

    変えるのは、最上位の項目と、版によって形を選ぶ部分の中の項目。ほかの部分
    （明細、合計、書類、出来事）は、スキーマの書き方を変えていない。
    """
    changed: list[tuple[str, Data]] = []
    for path in _every_key(data):
        if "." in path and not path.startswith(VERSIONED):
            continue
        for name, change in (
            ("delete", delp(path)),
            ("null", setp(path, None)),
            ("number", setp(path, 12345)),
            ("text", setp(path, "x")),
            ("list", setp(path, [])),
        ):
            copy_ = copy.deepcopy(data)
            change(copy_)
            changed.append((f"{name} {path}", copy_))
    for path in ("", "parties", "trade_terms", "transport", "transport.containers[0]", "lines[0]"):
        copy_ = copy.deepcopy(data)
        setp(f"{path}.surprise" if path else "surprise", 1)(copy_)
        changed.append((f"add {path}.surprise", copy_))
    return changed


@pytest.mark.parametrize("name", ["01_sea_fob_1c_1l", "10_multimodal_cpt_3c_5l"])
def test_v010_schema_part_is_equivalent_to_the_original_schema(
    original: Draft202012Validator, name: str
) -> None:
    """0.1.0 の見本を1か所ずつ変えた200通りほどで、いまのスキーマと、もとのスキーマの結果が同じ。"""
    data = load_json(SAMPLES_V010 / "valid" / f"{name}.json")
    checked = 0
    for label, changed in _mutations(data):
        if changed.get("contract_version") != "0.1.0":
            continue  # 版を変えた場合は、版の段で扱いが決まる（下のテスト）
        now = [(i.code, i.path) for i in schema_issues(changed, schema_validator())]
        before = [(i.code, i.path) for i in schema_issues(changed, original)]
        assert now == before, label
        checked += 1
    assert checked > 150


@pytest.mark.parametrize("folder", ["valid", "invalid"])
def test_v010_samples_give_the_same_schema_result_as_the_original(
    original: Draft202012Validator, folder: str
) -> None:
    for path in sorted((SAMPLES_V010 / folder).glob("*.json")):
        if path.name.endswith(".expected.json"):
            continue
        data = load_json(path)
        now = [(i.code, i.path) for i in schema_issues(data, schema_validator())]
        before = [(i.code, i.path) for i in schema_issues(data, original)]
        if data["contract_version"] == "0.1.0":
            assert now == before, path.name
        else:  # 版の不一致の誤り例：スキーマだけで調べても、知らない版として誤りになる
            assert ("ENUM_INVALID", "contract_version") in now, path.name


# ---- メッセージの中の shipment と、道具 ----


def _quote_request(shipment: Data) -> Data:
    planned = copy.deepcopy(shipment)  # 見積の時点：書類はまだない
    planned["status"] = "draft"
    planned["documents"] = []
    planned["events"] = planned["events"][:1]
    return new_message(
        "quote_request",
        {"shipment": planned, "reply_by": None, "note": None},
        sender={"role": "shipper", "name": "Demo Resource Recovery Co., Ltd.", "id": "test"},
        correlation_id=new_uuid(),
        sent_at=now_text(),
    )


@pytest.mark.parametrize("folder", [SAMPLES, SAMPLES_V010], ids=["0.1.1", "0.1.0"])
def test_messages_can_carry_a_shipment_of_either_version(folder: Path) -> None:
    """メッセージの中の shipment は、0.1.0 でも 0.1.1 でもよい。見本の相手側は両方を受け付ける。"""
    message = _quote_request(load_json(folder / "valid" / "03_sea_cif_3c_3l.json"))
    assert validate_message(message).valid

    outcome = broker_receiver().receive(message)
    assert outcome.state == COMPLETED
    assert outcome.artifacts[0]["message_type"] == "quote"


def test_message_reports_problems_in_the_added_items_of_its_shipment(base: Data) -> None:
    message = _quote_request(base)
    message["payload"]["shipment"]["trade_terms"]["freight_amount"] = "12"
    result = validate_message(message)
    assert [(issue.code, issue.path) for issue in result.errors] == [
        ("FORMAT_INVALID", "payload.shipment.trade_terms.freight_amount")
    ]


@pytest.mark.parametrize("folder", [SAMPLES, SAMPLES_V010], ids=["0.1.1", "0.1.0"])
def test_declaration_draft_can_be_built_from_either_version(folder: Path) -> None:
    """申告の下書き（模擬）は、どちらの版のデータからも作れる。足した項目は写さない。"""
    shipment = load_json(folder / "valid" / "03_sea_cif_3c_3l.json")
    draft = build_declaration_draft(shipment, "DD-TEST-1")
    assert draft["invoice_amount"] == shipment["totals"]["amount"]
    assert "freight_amount" not in json.dumps(draft)


# ---- 版そのものの扱い ----


def test_missing_or_malformed_version_reports_only_the_version(base: Data) -> None:
    """版が分からないときは、版によって形が変わる部分を当て推量で調べない。"""
    del base["contract_version"]
    del base["parties"]["consignee"]  # 版によって形が決まる部分の誤りは、版を直してから分かる
    assert pairs(base) == {("REQUIRED_MISSING", "contract_version")}

    base["contract_version"] = "v0.1.1"
    assert pairs(base) == {("FORMAT_INVALID", "contract_version")}
    base["contract_version"] = 0.1
    assert pairs(base) == {("TYPE_MISMATCH", "contract_version")}
    base["contract_version"] = LATEST_CONTRACT_VERSION
    assert pairs(base) == {("REQUIRED_MISSING", "parties.consignee")}


def test_version_independent_parts_are_checked_even_without_a_version(base: Data) -> None:
    del base["contract_version"]
    base["status"] = "shipped"
    base["lines"][0]["packages"] = "18"
    assert pairs(base) == {
        ("REQUIRED_MISSING", "contract_version"),
        ("ENUM_INVALID", "status"),
        ("TYPE_MISMATCH", "lines[0].packages"),
    }


@pytest.mark.parametrize("version", ["0.1.2", "0.2.0", "1.0.0"])
def test_schema_alone_rejects_a_version_it_does_not_know(base: Data, version: str) -> None:
    """スキーマだけで調べる人（検証B）にも、知らない版は誤りとして見える。"""
    base["contract_version"] = version
    found = [(i.code, i.path) for i in schema_issues(base, schema_validator())]
    assert found == [("ENUM_INVALID", "contract_version")]
    assert pairs(base) == {
        ("VERSION_UNSUPPORTED", "contract_version")
    }  # 検証コマンドでは版の不一致


def test_same_document_is_judged_by_its_own_version() -> None:
    """同じ中身でも、書いてある版で合否が決まる。"""
    new = load_json(SAMPLES / "valid" / "02_sea_cfr_2c_2l.json")
    old = load_json(SAMPLES_V010 / "valid" / "02_sea_cfr_2c_2l.json")
    assert validate_shipment(new).valid and validate_shipment(old).valid

    relabelled = {**old, "contract_version": "0.1.1"}  # 項目を足さずに、版だけ書き換えた
    assert pairs(relabelled) == {("REQUIRED_MISSING", path) for path in ADDED}
    relabelled = {**new, "contract_version": "0.1.0"}  # 足した項目を残したまま、版だけ戻した
    assert pairs(relabelled) == {("UNKNOWN_FIELD", path) for path in ADDED}
