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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def base() -> dict[str, Any]:
    """指示書 第13節の例（正しい例の1件目）。テストごとに新しく読み直す。"""
    return load_json(BASE_SAMPLE)
