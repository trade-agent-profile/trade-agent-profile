"""共通データ契約の古い版のデータを、新しい版の形に書き換える。

値は変えない。足された項目を「まだ分からない」（null。通知先は空の一覧）で足し、
contract_version を書き換えるだけ。ext の下に置いてある独自の値は動かさない
（正式の項目へ移すかどうかは、その値を置いたプロジェクトが決める）。

古い版のデータは、書き換えなくても検証に合格する。書き換えるのは、足された項目を
使いたいときだけでよい。
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from .validator import LATEST_CONTRACT_VERSION

Json = dict[str, Any]
_SECTIONS = ("parties", "trade_terms", "transport")


class UpgradeError(ValueError):
    """書き換えられないデータ。

    reason は理由の名前：not_object（オブジェクトでない）、version（対応していない版）、
    shape（当事者・取引条件・輸送のどれかがオブジェクトでない）。
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def _with_added(section: Json, added: Json, before: str | None = None) -> Json:
    """足された項目を入れた写しを作る。すでにある項目の値は変えない。

    before を渡すと、その項目の直前に入れる。なければ末尾に入れる。
    """
    fresh = {key: value for key, value in added.items() if key not in section}
    result: Json = {}
    placed = False
    for key, value in section.items():
        if key == before and not placed:
            result.update(fresh)
            placed = True
        result[key] = value
    if not placed:
        result.update(fresh)
    return result


def _to_0_1_1(data: Json) -> Json:
    """0.1.0 → 0.1.1：通知先、運賃と保険料の額、船名・航海番号・ブッキング番号を足す。"""
    data["parties"] = _with_added(data["parties"], {"notify_parties": []})
    data["trade_terms"] = _with_added(
        data["trade_terms"], {"freight_amount": None, "insurance_premium_amount": None}
    )
    data["transport"] = _with_added(
        data["transport"],
        {"vessel_name": None, "voyage_number": None, "booking_number": None},
        before="containers",
    )
    return data


# 版ごとの書き換え：もとの版 →（次の版、書き換える手順）
_STEPS: dict[str, tuple[str, Callable[[Json], Json]]] = {"0.1.0": ("0.1.1", _to_0_1_1)}
UPGRADABLE_FROM = tuple(_STEPS)


def upgrade_shipment(data: Any) -> Json:
    """shipment を、いまの版の形にした写しを返す。もとのデータは変えない。

    すでにいまの版なら、そのままの写しを返す。検証はしない（形を変えるだけなので、
    合計の不一致など、もとからある問題はそのまま残る）。
    """
    if not isinstance(data, dict):
        raise UpgradeError("not_object")
    version = data.get("contract_version")
    known = isinstance(version, str) and (version == LATEST_CONTRACT_VERSION or version in _STEPS)
    if not known:
        raise UpgradeError("version", str(version))
    result = copy.deepcopy(data)
    while result["contract_version"] != LATEST_CONTRACT_VERSION:
        for name in _SECTIONS:
            if not isinstance(result.get(name), dict):
                raise UpgradeError("shape", name)
        next_version, step = _STEPS[result["contract_version"]]
        result = step(result)
        result["contract_version"] = next_version
    return result
