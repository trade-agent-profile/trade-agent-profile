"""配布物（dist/contract-v0.1/）が正本と同じ中身であることを確かめる。"""

from __future__ import annotations

import build_dist

from trade_agent_profile import LATEST_CONTRACT_VERSION, SUPPORTED_CONTRACT_VERSIONS


def test_dist_matches_the_originals() -> None:
    files = build_dist.planned()
    # スキーマ1 +（正しい例10 + 誤り例10 + 期待結果10）× 2つの版（いまの版と 0.1.0）
    assert len(files) == 61
    for target, source in files.items():
        assert target.read_bytes() == source.read_bytes(), target.name
    assert build_dist.stale() == []


def test_dist_has_readme_and_changelog() -> None:
    readme = (build_dist.DIST / "README.ja.md").read_text(encoding="utf-8")
    changelog = (build_dist.DIST / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "これは実験的な参照仕様です。いずれの標準化団体の公式仕様でもありません。" in readme
    assert "0.1.0" in changelog
    # 配布物の説明と変更の記録が、いまの版のものであること
    for version in SUPPORTED_CONTRACT_VERSIONS:
        assert f"## {version}" in changelog, version
    assert f"v{LATEST_CONTRACT_VERSION}" in readme.splitlines()[0]
    for item in ("notify_parties", "freight_amount", "insurance_premium_amount", "vessel_name"):
        assert item in readme, item
