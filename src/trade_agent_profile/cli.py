"""検証コマンド。

入力にはファイル、フォルダ、複数ファイル、ワイルドカードを受け付ける。
PowerShell は外部コマンドに渡すワイルドカードを展開しないので、ここで展開する。
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import i18n
from .issues import ValidationResult
from .messages import validate_any_file
from .profile import SUPPORTED_PROFILE_VERSIONS
from .validator import SUPPORTED_CONTRACT_VERSIONS

EXIT_OK = 0
EXIT_NG = 1
EXIT_USAGE = 2

_SKIP_SUFFIXES = (".expected.json", ".schema.json")
_WILDCARD_CHARS = "*?["

Pair = tuple[str, str]


@dataclass
class Row:
    """1ファイル分の結果。"""

    path: Path
    result: ValidationResult
    expected_found: bool = True
    lacking: list[Pair] = field(default_factory=list)
    extra: list[Pair] = field(default_factory=list)

    @property
    def as_expected(self) -> bool:
        return self.expected_found and not self.lacking and not self.extra


def setup_stdio() -> None:
    """日本語が化けないように、出力の文字コードを整える。

    画面に直接出すときは Windows の仕組みに任せ、ファイルやほかのプログラムに
    渡すときは UTF-8 に固定する。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        if stream.isatty():
            reconfigure(errors="replace")
        else:
            reconfigure(encoding="utf-8", errors="replace")


def _is_target(path: Path) -> bool:
    name = path.name.lower()
    return path.is_file() and name.endswith(".json") and not name.endswith(_SKIP_SUFFIXES)


def expand_paths(args: list[str]) -> tuple[list[Path], list[str]]:
    """引数をファイルの一覧に広げる。何も見つからなかった引数も返す。"""
    files: list[Path] = []
    missing: list[str] = []
    for arg in args:
        path = Path(arg)
        if path.is_file():
            hits = [path]  # 名前を直接指定されたファイルは、そのまま調べる
        elif path.is_dir():
            hits = sorted(p for p in path.rglob("*.json") if _is_target(p))
        elif any(char in arg for char in _WILDCARD_CHARS):
            hits = sorted(p for p in map(Path, glob.glob(arg, recursive=True)) if _is_target(p))
        else:
            hits = []
        if not hits:
            missing.append(arg)
        for hit in hits:
            if hit not in files:
                files.append(hit)
    return files, missing


def _expected_path(path: Path) -> Path:
    return path.with_name(path.name[: -len(".json")] + ".expected.json")


def _compare_expected(row: Row) -> None:
    """対の .expected.json と、エラーの code と path の組を比べる。"""
    expected_file = _expected_path(row.path)
    if not expected_file.is_file():
        row.expected_found = False
        return
    expected = json.loads(expected_file.read_text(encoding="utf-8-sig"))
    want = {(item["code"], item["path"]) for item in expected.get("errors", [])}
    got = {(issue.code, issue.path) for issue in row.result.errors}
    row.lacking = sorted(want - got)
    row.extra = sorted(got - want)
    if expected.get("valid") is not row.result.valid and not row.lacking and not row.extra:
        row.extra = [("VALID_FLAG", "")]


def _ui(langs: tuple[str, ...], key: str, **params: object) -> str:
    return " / ".join(i18n.catalog(lang)["ui"][key].format(**params) for lang in langs)


def _print_issues(row: Row, langs: tuple[str, ...]) -> None:
    for number, issue in enumerate(row.result.errors, 1):
        where = issue.path or _ui(langs, "whole")
        labels = " / ".join(label for label in (issue.label(lang) for lang in langs) if label)
        suffix = f"  ({labels})" if labels and issue.path else ""
        print(f"  {number}) [{issue.code}] {where}{suffix}")
        for lang in langs:
            ui = i18n.catalog(lang)["ui"]
            print(f"     {ui['why']}: {issue.why(lang)}")
            print(f"     {ui['fix']}: {issue.fix(lang)}")


def _print_expected_detail(row: Row, langs: tuple[str, ...]) -> None:
    if not row.expected_found:
        print("  " + _ui(langs, "expected_missing_file"))
    for title, pairs in (("expected_lacking", row.lacking), ("expected_extra", row.extra)):
        for code, path in pairs:
            print(f"  {_ui(langs, title)}: [{code}] {path}")


def _report_text(rows: list[Row], langs: tuple[str, ...], quiet: bool, expected: bool) -> None:
    if not quiet:
        for lang in langs:
            print(i18n.catalog(lang)["ui"]["notice"])
        print()
    for row in rows:
        failed = not row.as_expected if expected else not row.result.valid
        if quiet and not failed:
            continue
        if expected:
            status = _ui(langs, "expected_ng" if failed else "expected_ok")
        else:
            status = _ui(langs, "ng" if failed else "ok")
        print(f"[{status}] {row.path}")
        if expected:
            _print_expected_detail(row, langs)
        else:
            _print_issues(row, langs)
    if not quiet:
        print()
    total = len(rows)
    if expected:
        good = sum(1 for row in rows if row.as_expected)
        key = "expected_summary"
    else:
        good = sum(1 for row in rows if row.result.valid)
        key = "summary"
    for lang in langs:
        print(i18n.catalog(lang)["ui"][key].format(total=total, ok=good, ng=total - good))
    if not quiet:
        for lang in langs:
            ui = i18n.catalog(lang)["ui"]
            print(ui["code_note"])
            print(ui["judge"])


def _report_json(rows: list[Row], expected: bool) -> None:
    results = []
    for row in rows:
        item = {"file": row.path.as_posix(), **row.result.to_dict()}
        if expected:
            item["as_expected"] = row.as_expected
        results.append(item)
    valid = sum(1 for row in rows if row.result.valid)
    payload = {
        "tool": "trade-agent-profile",
        "notice": {lang: i18n.catalog(lang)["ui"]["notice"] for lang in i18n.LANGS},
        "supported_contract_versions": list(SUPPORTED_CONTRACT_VERSIONS),
        "supported_profile_versions": list(SUPPORTED_PROFILE_VERSIONS),
        "summary": {"total": len(rows), "valid": valid, "invalid": len(rows) - valid},
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _run_validate(args: argparse.Namespace) -> int:
    langs = i18n.LANGS if args.lang == "both" else (args.lang,)
    files, missing = expand_paths(args.paths)
    if missing:
        for arg in missing:
            print(_ui(langs, "no_files", arg=arg), file=sys.stderr)
        return EXIT_USAGE

    rows = [Row(path, validate_any_file(path)) for path in files]
    if args.expected:
        for row in rows:
            _compare_expected(row)

    if args.as_json:
        _report_json(rows, args.expected)
    else:
        _report_text(rows, langs, args.quiet, args.expected)

    if args.expected:
        return EXIT_OK if all(row.as_expected for row in rows) else EXIT_NG
    return EXIT_OK if all(row.result.valid for row in rows) else EXIT_NG


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    parser = argparse.ArgumentParser(
        prog="trade-agent-profile",
        description=(
            "貿易用プロファイル（実験的な参照仕様）の道具 / "
            "Tools for the experimental trade agent profile"
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser(
        "validate", help="shipment.json を検証する / validate shipment.json files"
    )
    validate.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="ファイル、フォルダ、ワイルドカード / files, folders or wildcards",
    )
    validate.add_argument(
        "--lang",
        choices=("both", "ja", "en"),
        default="both",
        help="表示する言語（既定は両方） / language of messages (default: both)",
    )
    validate.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="結果を JSON で出す / print results as JSON",
    )
    validate.add_argument(
        "--expected",
        action="store_true",
        help="対の .expected.json と比べる / compare with paired .expected.json files",
    )
    validate.add_argument(
        "--quiet",
        action="store_true",
        help="問題のあるファイルと集計だけを出す / only show problems and the summary",
    )
    args = parser.parse_args(argv)
    return _run_validate(args)


if __name__ == "__main__":
    raise SystemExit(main())
