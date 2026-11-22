"""項目の場所（道筋）の書き方をそろえるための小さな道具。

道筋は指示書 第13節の書き方（totals.amount、lines[0].amount）に合わせる。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

Part = str | int

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SEGMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)((?:\[[0-9]+\])*)$")
_INDEX_RE = re.compile(r"\[([0-9]+)\]")


def format_path(parts: Iterable[Part]) -> str:
    """("lines", 0, "amount") を "lines[0].amount" の形にする。

    点やかっこを含む名前（fields のキーなど）は ["totals.amount"] のように囲む。
    """
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        elif _NAME_RE.match(part):
            out += f".{part}" if out else part
        else:
            escaped = part.replace("\\", "\\\\").replace('"', '\\"')
            out += f'["{escaped}"]'
    return out


def to_pointer(parts: Iterable[Part]) -> str:
    """JSON Pointer（RFC 6901）の形にする。機械で場所をたどるときに使う。"""
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def generic_path(parts: Iterable[Part]) -> str:
    """番号や自由な名前を伏せた形にする（表示名を引くための鍵）。

    例：("lines", 0, "amount") → "lines[].amount"
        ("documents", 0, "fields", "totals.amount", "value") → "documents[].fields.*.value"
    """
    out = ""
    wildcard_next = False
    for index, part in enumerate(parts):
        if isinstance(part, int):
            out += "[]"
            wildcard_next = False
        elif wildcard_next:
            out += ".*"
            wildcard_next = False
        else:
            out += f".{part}" if out else part
            wildcard_next = (part == "fields" and index >= 2) or (part == "ext" and index == 0)
    return out


def parse_field_path(text: str) -> list[Part] | None:
    """ "lines[0].amount" を ["lines", 0, "amount"] に分ける。形が違えば None。"""
    if not text:
        return None
    parts: list[Part] = []
    for segment in text.split("."):
        match = _SEGMENT_RE.match(segment)
        if not match:
            return None
        parts.append(match.group(1))
        parts.extend(int(index) for index in _INDEX_RE.findall(match.group(2)))
    return parts


def resolve(data: Any, parts: Iterable[Part]) -> tuple[bool, Any]:
    """道筋をたどって値を取り出す。(見つかったか, 値) を返す。"""
    current = data
    for part in parts:
        if isinstance(part, int):
            if not isinstance(current, list) or part >= len(current):
                return False, None
        elif not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current
