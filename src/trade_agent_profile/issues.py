"""検証で見つかった問題（Issue）と、その説明文の組み立て。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from . import i18n
from .paths import Part, format_path, generic_path, to_pointer

_MAX_SHOWN = 80


def _show(value: Any) -> str:
    """値を表示用の短い文字列にする。"""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= _MAX_SHOWN else text[: _MAX_SHOWN - 1] + "…"


@dataclass(frozen=True)
class Issue:
    """1件の問題。code と path の組で「何が・どこで」を表す。"""

    code: str
    parts: tuple[Part, ...] = ()
    params: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def path(self) -> str:
        """指示書 第13節と同じ書き方の場所（例 lines[0].amount）。"""
        return format_path(self.parts)

    @property
    def pointer(self) -> str:
        """JSON Pointer の形の場所（例 /lines/0/amount）。"""
        return to_pointer(self.parts)

    def label(self, lang: str) -> str | None:
        """項目の呼び名（例 合計金額）。なければ None。"""
        cat = i18n.catalog(lang)
        if self.parts[:2] == ("payload", "shipment") and len(self.parts) > 2:
            # メッセージに入った shipment の中は、契約（shipment.json）の呼び名を使う
            return cat["fields"].get(generic_path(self.parts[2:]))
        key = generic_path(self.parts)
        return cat["fields"].get(key) or cat["message_fields"].get(key)

    def why(self, lang: str) -> str:
        """なぜ違うか。"""
        return _describe(self, lang)[0]

    def fix(self, lang: str) -> str:
        """どう直すか。"""
        return _describe(self, lang)[1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "pointer": self.pointer,
            "label": {lang: self.label(lang) for lang in i18n.LANGS},
            "why": {lang: self.why(lang) for lang in i18n.LANGS},
            "fix": {lang: self.fix(lang) for lang in i18n.LANGS},
        }


@dataclass
class ValidationResult:
    """1件の shipment.json を検証した結果。"""

    errors: list[Issue] = field(default_factory=list)
    contract_version: str | None = None

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "contract_version": self.contract_version,
            "errors": [issue.to_dict() for issue in self.errors],
        }


def _describe(issue: Issue, lang: str) -> tuple[str, str]:
    """問題を「なぜ」「直し方」の2つの文にする。"""
    cat = i18n.catalog(lang)
    phrases = cat["phrases"]
    raw = issue.params
    params = {key: _show(value) for key, value in raw.items()}

    if issue.code == "FORMAT_INVALID":
        entry = cat["kinds"].get(raw.get("kind"), cat["kinds"]["generic"])
    else:
        entry = cat["errors"].get(issue.code, cat["errors"]["SCHEMA_VIOLATION"])

    if issue.code == "TYPE_MISMATCH":
        types = cat["types"]
        params["expected"] = phrases["or"].join(types.get(t, t) for t in raw.get("expected", []))
        params["actual"] = types.get(raw.get("actual"), str(raw.get("actual")))
        params["hint"] = cat["hints"].get(raw.get("hint"), "")
    elif issue.code == "ENUM_INVALID":
        params["allowed"] = phrases["list_sep"].join(str(v) for v in raw.get("allowed", []))
    elif issue.code == "ARRAY_LENGTH":
        low, high = raw.get("min"), raw.get("max")
        if low is not None and low == high:
            params["expected"] = phrases["exactly"].format(n=low)
        elif low is not None:
            params["expected"] = phrases["at_least"].format(n=low)
        else:
            params["expected"] = phrases["at_most"].format(n=high)
    elif issue.code == "OUT_OF_RANGE":
        low, high = raw.get("min"), raw.get("max")
        if low is not None and high is not None:
            params["range"] = phrases["range_both"].format(min=low, max=high)
        elif low is not None:
            params["range"] = phrases["range_min"].format(min=low)
        else:
            params["range"] = phrases["range_max"].format(max=high)
    elif issue.code == "FIELD_PATH_INVALID":
        params["reason"] = cat["reasons"].get(raw.get("reason"), "")
    elif issue.code == "JSON_INVALID":
        if raw.get("line"):
            params["where"] = phrases["json_at"].format(line=raw["line"], column=raw["column"])
        else:
            params["where"] = phrases["json_unknown"]

    why = i18n.render(entry["why"], params).strip()
    fix = i18n.render(entry["fix"], params).strip()
    return why, fix
