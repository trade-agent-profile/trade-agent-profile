"""shipment.json（共通データ契約 v0.1）の検証。

流れ：版の確認 → スキーマ（形・型・形式）→ 規則（検査数字、合計、日付の前後など）。
前の段で問題が見つかったら、後ろの段は行わない。
1つの原因から、似たエラーがいくつも出るのを防ぐため。

版は、データに書いてある contract_version で決まる。スキーマが、その版に合わせて
当事者・取引条件・輸送の形を選ぶ（0.1.1 で項目が足された）。0.1.0 のデータは、
0.1.0 の形のまま合格にする。
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .issues import Issue, ValidationResult
from .paths import Part
from .rules import run_rules

SUPPORTED_CONTRACT_VERSIONS = ("0.1.0", "0.1.1")
LATEST_CONTRACT_VERSION = SUPPORTED_CONTRACT_VERSIONS[-1]

_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_STRONG_CODES = ("REQUIRED_NULL", "TYPE_MISMATCH", "EXT_INVALID")
_JSON_TYPES = (
    (bool, "boolean"),
    (int, "integer"),
    (float, "number"),
    (str, "string"),
    (list, "array"),
    (dict, "object"),
)


@cache
def load_schema(name: str = "shipment") -> dict[str, Any]:
    """スキーマを読む。部品として入れた場合は同梱のもの、開発中は正本（schema/）を使う。

    name は "shipment"（共通データ契約）か "message"（メッセージの封筒と中身）。
    """
    here = Path(__file__).resolve().parent
    filename = f"{name}.schema.json"
    candidates = (here / "_data" / filename, here.parents[1] / "schema" / filename)
    for candidate in candidates:
        if candidate.is_file():
            with candidate.open(encoding="utf-8") as handle:
                return json.load(handle)
    raise FileNotFoundError(f"{filename} が見つかりません")


@cache
def schema_validator(name: str = "shipment") -> Draft202012Validator:
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_shipment(data: Any) -> ValidationResult:
    """読み込み済みのデータ（辞書）を検証する。"""
    if not isinstance(data, dict):
        return ValidationResult([Issue("ROOT_NOT_OBJECT")])

    version = data.get("contract_version")
    version = version if isinstance(version, str) else None
    if version and _VERSION_RE.match(version) and version not in SUPPORTED_CONTRACT_VERSIONS:
        params = {"value": version, "supported": ", ".join(SUPPORTED_CONTRACT_VERSIONS)}
        return ValidationResult(
            [Issue("VERSION_UNSUPPORTED", ("contract_version",), params)], version
        )

    issues = schema_issues(data, schema_validator())
    if not issues:
        issues = run_rules(data)
    return ValidationResult(issues, version)


def read_json(path: str | Path) -> tuple[Any, Issue | None]:
    """JSON ファイルを読む。読めないときは、例外ではなく問題として返す。"""
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        return None, Issue("FILE_UNREADABLE", (), {"detail": error.strerror or str(error)})
    try:
        text = raw.decode("utf-8-sig")  # 先頭の BOM はあっても読めるようにする
    except UnicodeDecodeError:
        return None, Issue("ENCODING_INVALID")
    try:
        return json.loads(text, parse_constant=_reject_constant), None
    except json.JSONDecodeError as error:
        params = {"line": error.lineno, "column": error.colno, "detail": error.msg}
        return None, Issue("JSON_INVALID", (), params)
    except ValueError as error:
        return None, Issue("JSON_INVALID", (), {"detail": str(error)})


def validate_file(path: str | Path) -> ValidationResult:
    """shipment.json のファイルを読んで検証する。"""
    data, problem = read_json(path)
    if problem is not None:
        return ValidationResult([problem])
    return validate_shipment(data)


def _reject_constant(name: str) -> None:
    raise ValueError(f"{name} is not a valid JSON value")


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    for python_type, name in _JSON_TYPES:
        if isinstance(value, python_type):
            return name
    return type(value).__name__


def _type_hint(expected: list[str], actual: str) -> str | None:
    if "string" in expected and actual in ("integer", "number"):
        return "decimal_string"
    if "integer" in expected and actual == "string":
        return "integer"
    return None


def schema_issues(data: Any, validator: Draft202012Validator) -> list[Issue]:
    """スキーマの違反を、利用者に説明しやすい形の問題に直す。"""
    found: dict[tuple[str, tuple[Part, ...]], Issue] = {}

    def add(code: str, parts: tuple[Part, ...], params: dict[str, Any] | None = None) -> None:
        found.setdefault((code, parts), Issue(code, parts, params or {}))

    for error in validator.iter_errors(data):
        parts: tuple[Part, ...] = tuple(error.absolute_path)
        keyword = error.validator
        if keyword == "required":
            for key in error.validator_value:
                if key not in error.instance:
                    add("REQUIRED_MISSING", (*parts, key), {"key": key})
        elif keyword == "additionalProperties":
            known = set(error.schema.get("properties", {}))
            for key in error.instance:
                if key not in known:
                    add("UNKNOWN_FIELD", (*parts, key), {"key": key})
        elif keyword == "type":
            if len(parts) == 2 and parts[0] == "ext":
                add("EXT_INVALID", parts, {"key": parts[1]})
            elif error.instance is None:
                add("REQUIRED_NULL", parts)
            else:
                value = error.validator_value
                expected = [value] if isinstance(value, str) else list(value)
                actual = _json_type(error.instance)
                hint = _type_hint(expected, actual)
                add("TYPE_MISMATCH", parts, {"expected": expected, "actual": actual, "hint": hint})
        elif keyword == "enum":
            params = {"value": error.instance, "allowed": list(error.validator_value)}
            add("ENUM_INVALID", parts, params)
        elif keyword == "const":
            params = {"value": error.instance, "allowed": [error.validator_value]}
            add("ENUM_INVALID", parts, params)
        elif keyword == "pattern":
            if "propertyNames" in error.absolute_schema_path:
                add("EXT_INVALID", (*parts, error.instance), {"key": error.instance})
            else:
                kind = error.schema.get("x-kind", "generic")
                add("FORMAT_INVALID", parts, {"value": error.instance, "kind": kind})
        elif keyword in ("minItems", "maxItems"):
            params = {
                "actual": len(error.instance),
                "min": error.schema.get("minItems"),
                "max": error.schema.get("maxItems"),
            }
            add("ARRAY_LENGTH", parts, params)
        elif keyword == "minLength":
            add("EMPTY_VALUE", parts)
        elif keyword in ("minimum", "maximum"):
            params = {
                "value": error.instance,
                "min": error.schema.get("minimum"),
                "max": error.schema.get("maximum"),
            }
            add("OUT_OF_RANGE", parts, params)
        else:
            add("SCHEMA_VIOLATION", parts, {"detail": error.message})

    # 型の間違いが出た場所では、ほかの細かいエラーを重ねて出さない
    strong = {issue.parts for issue in found.values() if issue.code in _STRONG_CODES}
    issues = [
        issue
        for issue in found.values()
        if issue.parts not in strong or issue.code in _STRONG_CODES
    ]
    return sorted(issues, key=lambda issue: (issue.pointer, issue.code))
