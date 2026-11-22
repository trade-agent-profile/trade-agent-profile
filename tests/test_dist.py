"""配布物（dist/contract-v0.1/）が正本と同じ中身であることを確かめる。"""

from __future__ import annotations

import build_dist


def test_dist_matches_the_originals() -> None:
    files = build_dist.planned()
    assert len(files) == 31  # スキーマ1 + 正しい例10 + 誤り例10 + 期待結果10
    for target, source in files.items():
        assert target.read_bytes() == source.read_bytes(), target.name
    assert build_dist.stale() == []


def test_dist_has_readme_and_changelog() -> None:
    readme = (build_dist.DIST / "README.ja.md").read_text(encoding="utf-8")
    changelog = (build_dist.DIST / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "これは実験的な参照仕様です。いずれの標準化団体の公式仕様でもありません。" in readme
    assert "0.1.0" in changelog
