"""ISO 6346 の検査数字。期待値はどれも手計算で確かめたもの。"""

from __future__ import annotations

import pytest

from trade_agent_profile import iso6346


def test_letter_values_skip_multiples_of_eleven() -> None:
    values = iso6346.LETTER_VALUES
    assert (values["A"], values["B"], values["K"], values["L"]) == (10, 12, 21, 23)
    assert (values["U"], values["V"], values["Z"]) == (32, 34, 38)
    assert not any(value % 11 == 0 for value in values.values())


@pytest.mark.parametrize(
    ("body", "digit"),
    [
        # C=13 S=30 Q=28 U=32 → 13 + 60 + 112 + 256 = 441
        # 3,0,5,4,3,8 → 48 + 0 + 320 + 512 + 768 + 4096 = 5744。合計 6185 = 11×562 + 3
        ("CSQU305438", 3),
        # 最後の桁が 9 → 合計 6697 = 11×608 + 9
        ("CSQU305439", 9),
        # 3,0,5,4,4,0 → 48 + 0 + 320 + 512 + 1024 + 0 = 1904。合計 2345 = 11×213 + 2
        ("CSQU305440", 2),
        # 0,0,1,0,0,0 → 64。合計 505 = 11×45 + 10。余り 10 は 0 にする
        ("CSQU001000", 0),
    ],
)
def test_check_digit(body: str, digit: int) -> None:
    assert iso6346.check_digit(body) == digit


def test_is_valid() -> None:
    assert iso6346.is_valid("CSQU3054383")  # 指示書の例
    assert not iso6346.is_valid("CSQU3054384")
    assert not iso6346.is_valid("CSQU305438")  # 桁が足りない
    assert not iso6346.is_valid("csqu3054383")  # 小文字


def test_check_digit_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError):
        iso6346.check_digit("CSQ3054383")
