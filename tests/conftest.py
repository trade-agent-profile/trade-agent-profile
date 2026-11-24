"""テスト共通の準備。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

SAMPLES = ROOT / "samples"
BASE_SAMPLE = SAMPLES / "valid" / "01_sea_fob_1c_1l.json"
# 前の版（契約 0.1.0）の見本。足した項目がないだけで、ほかは同じ
SAMPLES_V010 = SAMPLES / "v0.1.0"
BASE_SAMPLE_V010 = SAMPLES_V010 / "valid" / "01_sea_fob_1c_1l.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def base() -> dict[str, Any]:
    """指示書 第13節の例を、いまの版にしたもの（正しい例の1件目）。テストごとに読み直す。"""
    return load_json(BASE_SAMPLE)


@pytest.fixture
def base_v010() -> dict[str, Any]:
    """指示書 第13節の例そのもの（契約 0.1.0）。テストごとに読み直す。"""
    return load_json(BASE_SAMPLE_V010)
