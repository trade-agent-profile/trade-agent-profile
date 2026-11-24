"""検証の決まり。指示書の例を1か所ずつ変えて、出るエラーを確かめる。"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from typing import Any

import pytest

from trade_agent_profile import i18n, load_schema, validate_shipment
from trade_agent_profile.paths import parse_field_path

Data = dict[str, Any]
Change = Callable[[Data], None]
AMOUNT_KEY = "totals.amount"
AMOUNT_FIELD = 'documents[0].fields["totals.amount"]'
_UNFILLED = re.compile(r"\{[a-z_]+\}")


def setp(path: str, value: Any) -> Change:
    """道筋で指した場所の値を置き換える変更を作る。"""
    parts = parse_field_path(path)
    assert parts

    def change(data: Data) -> None:
        target: Any = data
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value

    return change


def delp(path: str) -> Change:
    parts = parse_field_path(path)
    assert parts

    def change(data: Data) -> None:
        target: Any = data
        for part in parts[:-1]:
            target = target[part]
        del target[parts[-1]]

    return change


def amount_field(key: str, value: Any) -> Change:
    """1件目の書類の totals.amount の読み取り結果を書き換える。"""

    def change(data: Data) -> None:
        data["documents"][0]["fields"][AMOUNT_KEY][key] = value

    return change


def rename_field_key(new_key: str) -> Change:
    def change(data: Data) -> None:
        fields = data["documents"][0]["fields"]
        fields[new_key] = fields.pop(AMOUNT_KEY)

    return change


def no_documents(data: Data) -> None:
    data["documents"] = []


def add_duplicate_container(data: Data) -> None:
    containers = data["transport"]["containers"]
    containers.append(copy.deepcopy(containers[0]))


def add_line_with_same_number(data: Data) -> None:
    data["lines"].append(copy.deepcopy(data["lines"][0]))
    data["totals"].update(
        amount="45000.00", net_weight_kg="36000.000", gross_weight_kg="36500.000", packages=36
    )
    data["documents"] = []


def add_discrepancy_event(data: Data) -> None:
    data["events"].append(
        {
            "type": "discrepancy_noted",
            "at": "2026-12-02T09:00:00+09:00",
            "by": "human",
            "note": "Invoice total differs from the shipment data.",
        }
    )


def add_unverified_hs_field(data: Data) -> None:
    fields = data["documents"][0]["fields"]
    fields["lines[0].hs_code_jp"] = copy.deepcopy(fields[AMOUNT_KEY]) | {"value": "000000000"}


CASES: list[tuple[str, list[Change], set[tuple[str, str]]]] = [
    ("変更なし", [], set()),
    # スキーマ：項目の過不足と型
    ("最上位の必須項目がない", [delp("shipment_id")], {("REQUIRED_MISSING", "shipment_id")}),
    (
        "入れ子の必須項目がない",
        [delp("parties.consignee")],
        {("REQUIRED_MISSING", "parties.consignee")},
    ),
    (
        "null にできる項目も省けない",
        [delp("lines[0].hs_code_jp")],
        {("REQUIRED_MISSING", "lines[0].hs_code_jp")},
    ),
    ("必須項目が null", [setp("status", None)], {("REQUIRED_NULL", "status")}),
    ("整数が文字列", [setp("lines[0].packages", "18")], {("TYPE_MISMATCH", "lines[0].packages")}),
    ("金額が数値", [setp("lines[0].amount", 22500.0)], {("TYPE_MISMATCH", "lines[0].amount")}),
    ("まとまりが文字列", [setp("parties", "x")], {("TYPE_MISMATCH", "parties")}),
    ("列挙値の外", [setp("status", "shipped")], {("ENUM_INVALID", "status")}),
    ("知らない最上位の項目", [setp("memo", "x")], {("UNKNOWN_FIELD", "memo")}),
    (
        "知らない入れ子の項目",
        [setp("lines[0].weight", "1")],
        {("UNKNOWN_FIELD", "lines[0].weight")},
    ),
    ("明細が0件", [setp("lines", [])], {("ARRAY_LENGTH", "lines")}),
    ("名称が空", [setp("parties.shipper.name", "")], {("EMPTY_VALUE", "parties.shipper.name")}),
    # スキーマ：形式
    (
        "港が3文字",
        [setp("transport.port_of_discharge", "SHA")],
        {("FORMAT_INVALID", "transport.port_of_discharge")},
    ),
    (
        "通貨が小文字",
        [setp("trade_terms.currency", "usd")],
        {("FORMAT_INVALID", "trade_terms.currency")},
    ),
    (
        "国が3文字",
        [setp("parties.shipper.country", "JPN")],
        {("FORMAT_INVALID", "parties.shipper.country")},
    ),
    (
        "金額が小数1桁",
        [setp("lines[0].amount", "22500.0")],
        {("FORMAT_INVALID", "lines[0].amount")},
    ),
    (
        "重量が小数4桁",
        [setp("lines[0].net_weight_kg", "18000.0000")],
        {("FORMAT_INVALID", "lines[0].net_weight_kg")},
    ),
    (
        "日付が斜線区切り",
        [setp("transport.etd", "2026/12/10")],
        {("FORMAT_INVALID", "transport.etd")},
    ),
    (
        "日時に時差がない",
        [setp("events[0].at", "2026-12-01T09:00:00")],
        {("FORMAT_INVALID", "events[0].at")},
    ),
    (
        "品目番号に点がある",
        [setp("lines[0].hs_code_jp", "7602.00")],
        {("FORMAT_INVALID", "lines[0].hs_code_jp")},
    ),
    ("船積みIDの形が違う", [setp("shipment_id", "SHP-26-1")], {("FORMAT_INVALID", "shipment_id")}),
    ("版の形が違う", [setp("contract_version", "v0.1")], {("FORMAT_INVALID", "contract_version")}),
    # スキーマ：ext と書類の読み取り結果
    (
        "ext の中身がオブジェクトでない",
        [setp("ext", {"myproj": "x"})],
        {("EXT_INVALID", "ext.myproj")},
    ),
    (
        "ext の名前が形式違反",
        [setp("ext", {"My Project": {}})],
        {("EXT_INVALID", 'ext["My Project"]')},
    ),
    ("ext の中身は自由", [setp("ext", {"my-project": {"any": [1, {"a": None}]}})], set()),
    (
        "bbox が3個",
        [amount_field("bbox", [1.0, 2.0, 3.0])],
        {("ARRAY_LENGTH", AMOUNT_FIELD + ".bbox")},
    ),
    (
        "確からしさが範囲の外",
        [amount_field("confidence", 1.5)],
        {("OUT_OF_RANGE", AMOUNT_FIELD + ".confidence")},
    ),
    (
        "読み取った値が null",
        [amount_field("value", None)],
        {("REQUIRED_NULL", AMOUNT_FIELD + ".value")},
    ),
    # 規則：日付
    (
        "実在しない日付",
        [setp("transport.etd", "2026-02-30")],
        {("FORMAT_INVALID", "transport.etd")},
    ),
    (
        "実在しない日時",
        [setp("events[0].at", "2026-12-01T25:00:00+09:00")],
        {("FORMAT_INVALID", "events[0].at")},
    ),
    ("到着が出発より前", [setp("transport.eta", "2026-12-09")], {("DATE_ORDER", "transport.eta")}),
    ("到着と出発が同じ日", [setp("transport.eta", "2026-12-10")], set()),
    ("日付が未定", [setp("transport.etd", None), setp("transport.eta", None)], set()),
    # 規則：当事者、コンテナ、明細
    (
        "輸出なのに輸出者が null",
        [setp("parties.exporter", None)],
        {("EXPORTER_REQUIRED", "parties.exporter")},
    ),
    (
        "輸入なら輸出者は null でよい",
        [setp("direction", "import"), setp("parties.exporter", None)],
        set(),
    ),
    (
        "検査数字が違う",
        [
            setp("transport.containers[0].number", "CSQU3054384"),
            setp("lines[0].container_number", "CSQU3054384"),
        ],
        {("CONTAINER_CHECK_DIGIT", "transport.containers[0].number")},
    ),
    (
        "同じコンテナが2回",
        [add_duplicate_container],
        {("CONTAINER_DUPLICATE", "transport.containers[1].number")},
    ),
    (
        "明細のコンテナが一覧にない",
        [setp("lines[0].container_number", "CSQU3054399")],
        {("LINE_CONTAINER_UNKNOWN", "lines[0].container_number")},
    ),
    ("コンテナに入れない貨物", [setp("lines[0].container_number", None)], set()),
    ("明細番号が重なる", [add_line_with_same_number], {("LINE_NO_DUPLICATE", "lines[1].line_no")}),
    # 規則：合計
    (
        "合計金額が違う",
        [no_documents, setp("totals.amount", "22050.00")],
        {("TOTAL_MISMATCH", "totals.amount")},
    ),
    ("合計の個数が違う", [setp("totals.packages", 17)], {("TOTAL_MISMATCH", "totals.packages")}),
    (
        "合計の総重量が違う",
        [setp("totals.gross_weight_kg", "18000.000")],
        {("TOTAL_MISMATCH", "totals.gross_weight_kg")},
    ),
    (
        "明細に null があれば合計は比べない",
        [setp("lines[0].net_weight_kg", None), setp("totals.net_weight_kg", "1.000")],
        set(),
    ),
    ("合計が null なら比べない", [setp("totals.packages", None)], set()),
    # 規則：書類の読み取り結果
    (
        "ai なのに確からしさがない",
        [amount_field("confidence", None)],
        {("CONFIDENCE_REQUIRED", AMOUNT_FIELD + ".confidence")},
    ),
    (
        "bbox の並びが逆",
        [amount_field("bbox", [520.0, 610.5, 400.0, 624.0])],
        {("BBOX_INVALID", AMOUNT_FIELD + ".bbox")},
    ),
    (
        "キーが道筋の形でない",
        [rename_field_key("totals..amount")],
        {("FIELD_PATH_INVALID", 'documents[0].fields["totals..amount"]')},
    ),
    (
        "キーの先に項目がない",
        [rename_field_key("lines[5].amount")],
        {("FIELD_PATH_INVALID", 'documents[0].fields["lines[5].amount"]')},
    ),
    (
        "キーがまとまりを指す",
        [rename_field_key("totals")],
        {("FIELD_PATH_INVALID", "documents[0].fields.totals")},
    ),
    (
        "キーが正本でない場所を指す",
        [rename_field_key("events[0].type")],
        {("FIELD_PATH_INVALID", 'documents[0].fields["events[0].type"]')},
    ),
    (
        "書類の値が正本と違い、記録がない",
        [amount_field("value", "22000.00")],
        {("DISCREPANCY_NOT_RECORDED", AMOUNT_FIELD)},
    ),
    (
        "書類の値が正本と違い、記録がある",
        [amount_field("value", "22000.00"), add_discrepancy_event],
        set(),
    ),
    ("金額は数として比べる", [amount_field("value", "22500.0")], set()),
    ("正本が null の項目とは比べない", [add_unverified_hs_field], set()),
    # 版
    (
        "扱えない版",
        [setp("contract_version", "0.2.0")],
        {("VERSION_UNSUPPORTED", "contract_version")},
    ),
    (
        "扱えない版なら、ほかの検査はしない",
        [setp("contract_version", "1.0.0"), setp("status", "shipped")],
        {("VERSION_UNSUPPORTED", "contract_version")},
    ),
]


@pytest.mark.parametrize(
    ("changes", "expected"), [case[1:] for case in CASES], ids=[case[0] for case in CASES]
)
def test_rules(base: Data, changes: list[Change], expected: set[tuple[str, str]]) -> None:
    for change in changes:
        change(base)
    result = validate_shipment(base)
    assert {(issue.code, issue.path) for issue in result.errors} == expected
    assert result.valid is (not expected)
    for issue in result.errors:
        for lang in i18n.LANGS:
            for text in (issue.why(lang), issue.fix(lang)):
                assert text
                assert not _UNFILLED.search(text), text


@pytest.mark.parametrize("data", [[], "text", 1, None])
def test_root_must_be_object(data: Any) -> None:
    result = validate_shipment(data)
    assert [(issue.code, issue.path) for issue in result.errors] == [("ROOT_NOT_OBJECT", "")]


def test_type_error_hides_other_errors_at_same_place(base: Data) -> None:
    base["status"] = 5
    result = validate_shipment(base)
    assert [(issue.code, issue.path) for issue in result.errors] == [("TYPE_MISMATCH", "status")]


def test_issue_to_dict_has_both_languages(base: Data) -> None:
    base["status"] = "shipped"
    item = validate_shipment(base).errors[0].to_dict()
    assert item["code"] == "ENUM_INVALID"
    assert item["pointer"] == "/status"
    assert item["label"] == {"ja": "状態", "en": "status"}
    assert "draft" in item["fix"]["ja"] and "draft" in item["fix"]["en"]


def _schema_paths(schema: dict[str, Any], root: dict[str, Any], prefix: str = "") -> set[str]:
    """スキーマに出てくる項目の場所を、番号を伏せた形で全部集める。"""
    if "$ref" in schema:
        target = root["$defs"][schema["$ref"].rsplit("/", 1)[-1]]
        schema = {**target, **{k: v for k, v in schema.items() if k != "$ref"}}
    paths: set[str] = set()
    for key, sub in schema.get("properties", {}).items():
        path = f"{prefix}.{key}" if prefix else key
        paths.add(path)
        paths |= _schema_paths(sub, root, path)
    if isinstance(schema.get("items"), dict):
        paths.add(prefix + "[]")
        paths |= _schema_paths(schema["items"], root, prefix + "[]")
    if isinstance(schema.get("additionalProperties"), dict):
        paths.add(prefix + ".*")
        paths |= _schema_paths(schema["additionalProperties"], root, prefix + ".*")
    for branch in schema.get("allOf", []):  # 版や種類ごとに形を選ぶ部分も集める
        if isinstance(branch.get("then"), dict):
            paths |= _schema_paths(branch["then"], root, prefix)
    return paths


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_every_item_has_a_label(lang: str) -> None:
    schema = load_schema()
    assert _schema_paths(schema, schema) == set(i18n.catalog(lang)["fields"])


def test_catalogs_have_the_same_keys() -> None:
    ja, en = i18n.catalog("ja"), i18n.catalog("en")
    for section in ("ui", "types", "phrases", "hints", "reasons", "errors", "kinds", "fields"):
        assert set(ja[section]) == set(en[section]), section


def test_every_format_kind_has_a_message() -> None:
    schema = load_schema()
    kinds = {
        definition["x-kind"] for definition in schema["$defs"].values() if "x-kind" in definition
    }
    for lang in i18n.LANGS:
        assert kinds <= set(i18n.catalog(lang)["kinds"])
