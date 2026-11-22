"""ISO 6346 のコンテナ番号の検査数字。

計算の決まり：
- 英字は A=10 から順に数を割り当てる。ただし 11 の倍数（11, 22, 33）は飛ばす。
- 先頭10文字のそれぞれに、左から 1, 2, 4, 8, …（2 の累乗）を掛けて足す。
- 合計を 11 で割った余りが検査数字。余りが 10 のときは 0 とする。
"""

from __future__ import annotations

import re


def _letter_values() -> dict[str, int]:
    values: dict[str, int] = {}
    number = 10
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if number % 11 == 0:
            number += 1
        values[letter] = number
        number += 1
    return values


LETTER_VALUES = _letter_values()
_BODY_RE = re.compile(r"^[A-Z]{4}[0-9]{6}$")
_FULL_RE = re.compile(r"^[A-Z]{4}[0-9]{7}$")


def check_digit(body: str) -> int:
    """先頭10文字（英字4文字＋数字6桁）から検査数字を求める。"""
    if not _BODY_RE.match(body):
        raise ValueError(f"英字4文字＋数字6桁ではありません: {body!r}")
    total = 0
    for position, char in enumerate(body):
        value = LETTER_VALUES[char] if char.isalpha() else int(char)
        total += value * 2**position
    return total % 11 % 10


def is_valid(number: str) -> bool:
    """11文字のコンテナ番号の検査数字が合っているかを返す。"""
    return bool(_FULL_RE.match(number)) and check_digit(number[:10]) == int(number[10])
