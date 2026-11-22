"""検証コマンド。ファイル・フォルダ・ワイルドカードの受け付けと、表示を確かめる。"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from conftest import ROOT, SAMPLES

from trade_agent_profile.cli import EXIT_NG, EXIT_OK, EXIT_USAGE, expand_paths, main

VALID_DIR = SAMPLES / "valid"
INVALID_DIR = SAMPLES / "invalid"
NOTICE_JA = "これは実験的な参照仕様です。いずれの標準化団体の公式仕様でもありません。"
JUDGE_JA = "判断するのは利用者です。このツールは下調べと記録を担います。"


def test_folder(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(VALID_DIR)]) == EXIT_OK
    out = capsys.readouterr().out
    assert NOTICE_JA in out
    assert JUDGE_JA in out
    assert "10件を調べました。合格 10件、不合格 0件。" in out
    assert "Checked 10 file(s): 10 valid, 0 invalid." in out


def test_wildcard_is_expanded_by_the_command() -> None:
    files, missing = expand_paths([str(VALID_DIR / "*.json")])
    assert len(files) == 10
    assert not missing


def test_wildcard_skips_expected_files() -> None:
    files, _ = expand_paths([str(INVALID_DIR / "*.json")])
    assert len(files) == 10
    assert not any(path.name.endswith(".expected.json") for path in files)


def test_multiple_files_and_duplicates() -> None:
    first, second = sorted(VALID_DIR.glob("*.json"))[:2]
    files, _ = expand_paths([str(first), str(second), str(first)])
    assert files == [first, second]


def test_invalid_folder_shows_why_and_how_to_fix(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(INVALID_DIR)]) == EXIT_NG
    out = capsys.readouterr().out
    assert "10件を調べました。合格 0件、不合格 10件。" in out
    assert "[CONTAINER_CHECK_DIGIT] transport.containers[0].number" in out
    assert "コンテナ番号" in out and "container number" in out
    assert "なぜ:" in out and "直し方:" in out
    assert "Why:" in out and "Fix:" in out


def test_single_language(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(INVALID_DIR), "--lang", "ja"]) == EXIT_NG
    out = capsys.readouterr().out
    assert "なぜ:" in out
    assert "Why:" not in out


def test_expected_mode(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(INVALID_DIR), "--expected", "--quiet"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "期待どおり 10件" in out
    # 正しい例には期待結果のファイルがないので、比べると失敗になる
    assert main(["validate", str(VALID_DIR), "--expected", "--quiet"]) == EXIT_NG


def test_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(INVALID_DIR), "--json"]) == EXIT_NG
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"total": 10, "valid": 0, "invalid": 10}
    assert payload["notice"]["ja"] == NOTICE_JA
    error = payload["results"][0]["errors"][0]
    assert set(error) == {"code", "path", "pointer", "label", "why", "fix"}


def test_nothing_found(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(ROOT / "no-such-folder" / "*.json")]) == EXIT_USAGE
    assert "見つかりません" in capsys.readouterr().err


def test_broken_json_is_reported_not_raised(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text('{"contract_version": "0.1.0",', encoding="utf-8")
    not_utf8 = tmp_path / "sjis.json"
    not_utf8.write_bytes('{"名前": 1}'.encode("cp932"))
    assert main(["validate", str(tmp_path)]) == EXIT_NG
    out = capsys.readouterr().out
    assert "[JSON_INVALID]" in out
    assert "[ENCODING_INVALID]" in out


def test_script_entry_writes_utf8_when_piped() -> None:
    """ほかのプログラムに渡すときは、PC の設定に関係なく UTF-8 で出す。"""
    done = subprocess.run(
        [sys.executable, "scripts/validate.py", "samples/valid", "--quiet", "--lang", "ja"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert done.returncode == EXIT_OK
    assert "合格 10件" in done.stdout.decode("utf-8")
