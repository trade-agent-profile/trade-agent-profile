"""古い版（契約 0.1.0）のデータを、いまの版の形に書き換える道具。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from conftest import SAMPLES, SAMPLES_V010, load_json

from trade_agent_profile import (
    LATEST_CONTRACT_VERSION,
    UpgradeError,
    i18n,
    upgrade_shipment,
    validate_shipment,
)
from trade_agent_profile.cli import main

Data = dict[str, Any]
OLD_FILES = sorted((SAMPLES_V010 / "valid").glob("*.json"))


@pytest.mark.parametrize("path", OLD_FILES, ids=lambda p: p.stem)
def test_upgraded_sample_is_valid_and_keeps_every_value(path: Path) -> None:
    old = load_json(path)
    before = copy.deepcopy(old)
    new = upgrade_shipment(old)

    assert old == before  # もとのデータは変えない
    assert new["contract_version"] == LATEST_CONTRACT_VERSION
    assert validate_shipment(new).valid
    assert new["parties"]["notify_parties"] == []
    assert new["trade_terms"]["freight_amount"] is None
    assert new["trade_terms"]["insurance_premium_amount"] is None
    for key in ("vessel_name", "voyage_number", "booking_number"):
        assert new["transport"][key] is None
    # 足した項目のほかは、1つも変わっていない
    for key, value in old.items():
        if key in ("contract_version", "parties", "trade_terms", "transport"):
            continue
        assert new[key] == value, key
    for section in ("parties", "trade_terms", "transport"):
        for key, value in old[section].items():
            assert new[section][key] == value, (section, key)


def test_added_items_are_placed_where_the_samples_have_them(base_v010: Data, base: Data) -> None:
    """書き換えた結果は、項目の並び順まで、いまの版の見本と同じになる。"""
    new = upgrade_shipment(base_v010)
    assert json.dumps(new) == json.dumps(base)
    assert list(new["transport"])[-1] == "containers"  # 一覧は、輸送のいちばん後ろのまま


def test_upgrading_the_current_version_changes_nothing(base: Data) -> None:
    again = upgrade_shipment(base)
    assert again == base and again is not base


def test_upgrade_does_not_judge_the_content(base_v010: Data) -> None:
    """形を変えるだけなので、もとからある問題（合計の不一致など）はそのまま残る。"""
    base_v010["totals"]["amount"] = "1.00"
    new = upgrade_shipment(base_v010)
    before = [(issue.code, issue.path) for issue in validate_shipment(base_v010).errors]
    after = [(issue.code, issue.path) for issue in validate_shipment(new).errors]
    assert ("TOTAL_MISMATCH", "totals.amount") in before
    assert after == before  # 書き換えで、問題が増えも減りもしない


def test_upgrade_keeps_a_value_that_is_already_there(base_v010: Data) -> None:
    """足す項目と同じ名前の値がすでにあれば、その値を消さない。"""
    base_v010["transport"]["vessel_name"] = "SAMPLE EXPRESS"
    assert upgrade_shipment(base_v010)["transport"]["vessel_name"] == "SAMPLE EXPRESS"


def test_upgrade_does_not_move_values_under_ext(base_v010: Data) -> None:
    base_v010["ext"] = {"p26": {"notify_party": {"name": "Sample Notify Co., Ltd."}}}
    new = upgrade_shipment(base_v010)
    assert new["ext"] == base_v010["ext"]
    assert new["parties"]["notify_parties"] == []  # 正式の項目へ移すのは、値を置いた側が行う


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        ([], "not_object"),
        ("text", "not_object"),
        ({}, "version"),
        ({"contract_version": "0.2.0"}, "version"),
        ({"contract_version": ["0.1.0"]}, "version"),
        ({"contract_version": "0.1.0"}, "shape"),
        ({"contract_version": "0.1.0", "parties": {}, "trade_terms": {}, "transport": []}, "shape"),
    ],
)
def test_upgrade_refuses_what_it_cannot_handle(data: Any, reason: str) -> None:
    with pytest.raises(UpgradeError) as caught:
        upgrade_shipment(data)
    assert caught.value.reason == reason


# ---- 命令（scripts\upgrade.py） ----


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    code = main(["upgrade", *args])
    return code, capsys.readouterr().out


def test_command_writes_upgraded_copies_and_leaves_the_sources(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "upgraded"
    before = {path.name: path.read_bytes() for path in OLD_FILES}
    code, text = run(capsys, str(SAMPLES_V010 / "valid"), "--out", str(out), "--lang", "ja")

    ui = i18n.catalog("ja")["ui"]
    assert code == 0
    assert ui["notice"] in text and ui["judge"] in text and ui["upgrade_note"] in text
    assert ui["upgrade_summary"].format(total=10, done=10, same=0, exists=0, failed=0) in text
    assert text.count(ui["upgrade_check_ok"]) == 10
    assert {path.name: path.read_bytes() for path in OLD_FILES} == before  # もとは変えない
    written = sorted(out.glob("*.json"))
    assert [path.name for path in written] == sorted(before)
    for path in written:
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf") and b"\r\n" not in raw  # BOM なし・改行は LF
        assert validate_shipment(json.loads(raw)).valid
    first = out / "01_sea_fob_1c_1l.json"
    assert first.read_bytes() == (SAMPLES / "valid" / first.name).read_bytes()


def test_command_never_overwrites(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = SAMPLES_V010 / "valid" / "01_sea_fob_1c_1l.json"
    target = tmp_path / source.name
    target.write_text("keep me", encoding="utf-8")
    code, text = run(capsys, str(source), "--out", str(tmp_path), "--lang", "ja")
    assert code == 1
    assert target.read_text(encoding="utf-8") == "keep me"
    assert i18n.catalog("ja")["ui"]["upgrade_exists"] in text


def test_command_reports_files_it_cannot_upgrade(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{ not json", encoding="utf-8")
    out = tmp_path / "out"
    code, text = run(
        capsys,
        str(SAMPLES / "valid" / "01_sea_fob_1c_1l.json"),  # すでにいまの版
        str(SAMPLES / "messages" / "01_quote_request.json"),  # メッセージ
        str(SAMPLES_V010 / "invalid" / "09_version_mismatch.json"),  # 対応していない版
        str(broken),
        "--out",
        str(out),
    )
    assert code == 1
    for lang in i18n.LANGS:  # 言語を指定しなければ、日本語と英語の両方で出る
        ui = i18n.catalog(lang)["ui"]
        assert ui["upgrade_same_detail"].format(version=LATEST_CONTRACT_VERSION) in text
        assert ui["upgrade_reason_message"] in text
        assert ui["upgrade_reason_unreadable"] in text
        assert ui["upgrade_summary"].format(total=4, done=0, same=1, exists=0, failed=3) in text
    assert "0.2.0" in text
    assert not out.exists()  # 書き出すものがなければ、フォルダも作らない


def test_command_needs_an_output_folder_and_existing_inputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["upgrade", str(SAMPLES_V010 / "valid")])
    assert stopped.value.code == 2
    capsys.readouterr()
    assert main(["upgrade", str(tmp_path / "nothing-here"), "--out", str(tmp_path / "o")]) == 2
