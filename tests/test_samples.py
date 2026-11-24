"""見本（samples/）が M1 の完成条件を満たしていることを確かめる。"""

from __future__ import annotations

import re
from pathlib import Path

import make_samples
import pytest
from conftest import ROOT, SAMPLES, SAMPLES_V010, load_json

from trade_agent_profile import LATEST_CONTRACT_VERSION, upgrade_shipment, validate_file

VALID = sorted((SAMPLES / "valid").glob("*.json"))
INVALID = sorted(
    p for p in (SAMPLES / "invalid").glob("*.json") if not p.name.endswith(".expected.json")
)
EXPECTED = sorted((SAMPLES / "invalid").glob("*.expected.json"))
# 前の版（契約 0.1.0）の見本。いまの版の検証でも、そのまま同じ結果になること
OLD_VALID = sorted((SAMPLES_V010 / "valid").glob("*.json"))
OLD_INVALID = sorted(
    p for p in (SAMPLES_V010 / "invalid").glob("*.json") if not p.name.endswith(".expected.json")
)


def _expected_of(path: Path) -> Path:
    return path.with_name(path.stem + ".expected.json")


def _id(path: Path) -> str:
    return f"{path.parent.parent.name}-{path.stem}" if "v0.1.0" in path.parts else path.stem


def test_counts() -> None:
    assert len(VALID) == 10
    assert len(INVALID) == 10
    assert len(EXPECTED) == 10
    assert len(OLD_VALID) == 10
    assert len(OLD_INVALID) == 10


def test_samples_carry_the_version_of_their_folder() -> None:
    assert {load_json(path)["contract_version"] for path in VALID} == {LATEST_CONTRACT_VERSION}
    assert {load_json(path)["contract_version"] for path in OLD_VALID} == {"0.1.0"}


@pytest.mark.parametrize("path", VALID + OLD_VALID, ids=_id)
def test_valid_samples_pass(path: Path) -> None:
    result = validate_file(path)
    assert result.valid, [(issue.code, issue.path) for issue in result.errors]


@pytest.mark.parametrize("path", INVALID + OLD_INVALID, ids=_id)
def test_invalid_samples_fail_as_expected(path: Path) -> None:
    expected = load_json(_expected_of(path))
    result = validate_file(path)
    assert expected["valid"] is False
    assert not result.valid
    want = {(item["code"], item["path"]) for item in expected["errors"]}
    assert {(issue.code, issue.path) for issue in result.errors} == want


def test_each_invalid_sample_has_one_distinct_kind_of_error() -> None:
    codes = []
    for path in EXPECTED:
        errors = load_json(path)["errors"]
        assert len(errors) == 1, path.name
        codes.append(errors[0]["code"])
    assert len(set(codes)) == 10


def test_valid_samples_cover_the_required_variety() -> None:
    data = [load_json(path) for path in VALID]
    assert {len(item["transport"]["containers"]) for item in data} == {0, 1, 2, 3}
    assert {len(item["lines"]) for item in data} == {1, 2, 3, 4, 5}
    assert len({item["transport"]["mode"] for item in data}) >= 3
    assert len({item["trade_terms"]["incoterms"] for item in data}) >= 6
    assert len({item["shipment_id"] for item in data}) == 10


def _parties(data: dict) -> list[dict]:
    """当事者を1件ずつ取り出す（通知先は一覧なので、中身を並べる）。"""
    found = []
    for value in data["parties"].values():
        found += value if isinstance(value, list) else [value]
    return found


def test_samples_are_marked_as_fictional() -> None:
    marker = re.compile(r"Sample|Example|Demo|SAMPLE|EXAMPLE|DEMO")
    for path in VALID + INVALID + OLD_VALID + OLD_INVALID:
        data = load_json(path)
        for party in _parties(data):
            assert marker.search(party["name"]), path.name
        for key in ("vessel_name", "booking_number"):  # 0.1.1 で足した項目も架空と分かる値にする
            value = data["transport"].get(key)
            assert value is None or marker.search(value), path.name
        for line in data["lines"]:
            assert "(sample)" in line["description"], path.name
            assert line["hs_code_jp"] is None and line["hs_code_dest"] is None, path.name


def test_new_items_are_shown_both_filled_and_empty() -> None:
    """0.1.1 で足した項目は、値の入った例と、まだ分からない（null・空）例の両方があること。"""
    data = [load_json(path) for path in VALID]
    counts = {len(item["parties"]["notify_parties"]) for item in data}
    assert {0, 1, 2} <= counts
    for section, key in (
        ("trade_terms", "freight_amount"),
        ("trade_terms", "insurance_premium_amount"),
        ("transport", "vessel_name"),
        ("transport", "voyage_number"),
        ("transport", "booking_number"),
    ):
        values = [item[section][key] for item in data]
        assert any(value is None for value in values), key
        assert any(value is not None for value in values), key
    # 海上でない見本には、船名と航海番号を入れていない
    for item in data:
        if item["transport"]["mode"] == "air":
            assert item["transport"]["vessel_name"] is None
            assert item["transport"]["voyage_number"] is None


@pytest.mark.parametrize("path", OLD_VALID, ids=lambda p: p.stem)
def test_old_sample_is_the_new_sample_without_the_added_items(path: Path) -> None:
    """0.1.0 の見本と 0.1.1 の見本は、足した項目のほかは同じ。

    足した項目に値を入れていない見本は、0.1.0 の見本を書き換えると 0.1.1 の見本と同じになる。
    """
    old, new = load_json(path), load_json(SAMPLES / "valid" / path.name)
    assert make_samples.to_v010(new) == old
    upgraded = upgrade_shipment(old)
    assert make_samples.to_v010(upgraded) == old  # 書き換えは、もとからある値を変えない
    added_is_empty = (
        new["parties"]["notify_parties"] == []
        and all(new["trade_terms"][key] is None for key in make_samples.ADDED_0_1_1["trade_terms"])
        and all(new["transport"][key] is None for key in make_samples.ADDED_0_1_1["transport"])
    )
    assert (upgraded == new) is added_is_empty


def test_samples_match_the_generator() -> None:
    """samples/ の中身が、作る道具（scripts/make_samples.py）の出力と同じであること。"""
    files = make_samples.build_all()
    for relative, text in files.items():
        with (ROOT / relative).open(encoding="utf-8", newline="") as handle:
            assert handle.read() == text, relative
    on_disk = {path.relative_to(ROOT).as_posix() for path in SAMPLES.rglob("*.json")}
    assert on_disk == {name for name in files if name.startswith("samples/")}
