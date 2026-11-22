"""表示の文言（日本語・英語）。文言は locales/ の JSON に集めてある。"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

LANGS = ("ja", "en")
_LOCALE_DIR = Path(__file__).parent / "locales"


@cache
def catalog(lang: str) -> dict[str, Any]:
    """1つの言語の文言をまとめて読む。"""
    with (_LOCALE_DIR / f"{lang}.json").open(encoding="utf-8") as handle:
        return json.load(handle)


class _KeepMissing(dict):
    """埋める値がない場所は、そのまま {名前} として残す。"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render(template: str, params: dict[str, Any]) -> str:
    """文言の {名前} の場所に値を埋める。"""
    return template.format_map(_KeepMissing(params))
