"""見本（samples/）が M1 の完成条件を満たしていることを確かめる。"""

from __future__ import annotations

import re
from pathlib import Path

import make_samples
import pytest
from conftest import ROOT, SAMPLES, load_json

from trade_agent_profile import validate_file

VALID = sorted((SAMPLES / "valid").glob("*.json"))
INVALID = sorted(
    p for p in (SAMPLES / "invalid").glob("*.json") if not p.name.endswith(".expected.json")
)
EXPECTED = sorted((SAMPLES / "invalid").glob("*.expected.json"))


def _expected_of(path: Path) -> Path:
    return path.with_name(path.stem + ".expected.json")


def test_counts() -> None:
    assert len(VALID) == 10
    assert len(INVALID) == 10
    assert len(EXPECTED) == 10


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_valid_samples_pass(path: Path) -> None:
    result = validate_file(path)
    assert result.valid, [(issue.code, issue.path) for issue in result.errors]


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
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


def test_samples_are_marked_as_fictional() -> None:
    marker = re.compile(r"Sample|Example|Demo")
    for path in VALID + INVALID:
        data = load_json(path)
        for party in data["parties"].values():
            assert marker.search(party["name"]), path.name
        for line in data["lines"]:
            assert "(sample)" in line["description"], path.name
            assert line["hs_code_jp"] is None and line["hs_code_dest"] is None, path.name


def test_samples_match_the_generator() -> None:
    """samples/ の中身が、作る道具（scripts/make_samples.py）の出力と同じであること。"""
    files = make_samples.build_all()
    for relative, text in files.items():
        with (ROOT / relative).open(encoding="utf-8", newline="") as handle:
            assert handle.read() == text, relative
    on_disk = {path.relative_to(ROOT).as_posix() for path in SAMPLES.rglob("*.json")}
    assert on_disk == {name for name in files if name.startswith("samples/")}
