"""公開前の検査（src/trade_agent_profile/prepublish.py）。

試すための git の置き場は、一時フォルダに作る。利用者の git の設定（名前とメールアドレス）を
読まないように、git の設定ファイルを空のものに差し替えてから使う。
疑わしい文字列は、このファイル自身が検査に引っかからないよう、実行するときに組み立てる。
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from trade_agent_profile import prepublish

FAKE_KEY = "AKIA" + "Q" * 16
PERSONAL_MAIL = "persona.fictional" + "@" + "mail.co.jp"
PHONE = "03" + "-1234-5678"
USER_PATH = "C:" + "\\Users\\" + "fictional-user" + "\\Desktop"
# 実在の人の名前に当たらないよう、人名らしくない語にしてある
NAME = "Fictional " + "Persona"
NAME_FULL_WIDTH = "Ｆｉｃｔｉｏｎａｌ　Ｐｅｒｓｏｎａ"
MAINTAINER = "Test Maintainer"


class Repo:
    """一時フォルダの中の、試すための git の置き場。"""

    def __init__(self, root: Path, home: Path) -> None:
        self.root = root
        self.config = home / "empty.gitconfig"
        self.config.write_text("", encoding="utf-8")
        root.mkdir()
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str, author: str = MAINTAINER) -> None:
        env = dict(os.environ)
        env.update(
            GIT_CONFIG_GLOBAL=str(self.config),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME=author,
            GIT_AUTHOR_EMAIL="maintainer@example.invalid",
            GIT_COMMITTER_NAME=author,
            GIT_COMMITTER_EMAIL="maintainer@example.invalid",
        )
        subprocess.run(["git", *args], cwd=self.root, env=env, check=True, capture_output=True)

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, message: str, author: str = MAINTAINER) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message, author=author)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path / "repo", tmp_path)


def _sample(name: str, description: str) -> str:
    return json.dumps({"parties": {"shipper": {"name": name}}, "lines": [{"description": description}]})


def test_clean_repository_has_nothing(repo: Repo) -> None:
    repo.write("README.md", "連絡先の例: someone@example.com\n置き場所の例: C:\\Users\\<名前>\\Desktop\n")
    repo.write("samples/valid/a.json", _sample("Sample Metal K.K.", "Copper scrap (sample)"))
    repo.commit("最初の版\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    result = prepublish.scan_repository(repo.root)
    assert result.findings == []
    assert (result.files, result.history_blobs, result.commits) == (2, 0, 1)


def test_finds_each_kind_in_current_files(repo: Repo) -> None:
    lines = ["ok", f"key = {FAKE_KEY}", f"mail {PERSONAL_MAIL}", f"tel {PHONE}", f"at {USER_PATH}"]
    repo.write("notes.txt", "\n".join(lines) + "\n")
    repo.write(".env", "TOKEN=x\n")
    repo.write("scan.pdf", "%PDF-1.4\n")
    repo.write("samples/valid/a.json", _sample("Real Metal Co.", "Copper scrap"))
    repo.commit("add")
    result = prepublish.scan_repository(repo.root)
    found = {(f.category, f.path, f.line, f.field_path) for f in result.findings}
    assert found == {
        ("secret", "notes.txt", 2, ""),
        ("email", "notes.txt", 3, ""),
        ("phone", "notes.txt", 4, ""),
        ("user_path", "notes.txt", 5, ""),
        ("tracked_private", ".env", None, ""),
        ("document_file", "scan.pdf", None, ""),
        ("sample_marker", "samples/valid/a.json", None, "parties.shipper.name"),
        ("sample_marker", "samples/valid/a.json", None, "lines[0].description"),
    }
    assert all(f.where == "file" for f in result.findings)


def test_history_and_commit_messages_are_checked(repo: Repo) -> None:
    repo.write("config.txt", f"key = {FAKE_KEY}\n")
    repo.write(".env.local", "X=1\n")
    repo.commit(f"連絡は {PERSONAL_MAIL} へ")
    repo.write("config.txt", "key = (removed)\n")
    repo.git("rm", "-q", "--cached", ".env.local")
    (repo.root / ".env.local").unlink()
    repo.commit("消した")
    result = prepublish.scan_repository(repo.root)
    kinds = {(f.category, f.where, f.path) for f in result.findings}
    assert kinds == {
        ("secret", "history", "config.txt"),
        ("tracked_private", "history", ".env.local"),
        ("email", "commit_message", ""),
    }
    secret = next(f for f in result.findings if f.category == "secret")
    assert secret.line == 1 and len(secret.blob) == 7


def test_stage1_reads_only_tracked_files(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    repo.write(".gitignore", "data/private/\n")
    repo.write("data/private/names.txt", f"{NAME}\n")
    repo.write("README.md", "hello\n")
    repo.commit("first")
    opened: list[str] = []
    original = Path.read_bytes

    def spy(self: Path) -> bytes:
        opened.append(self.as_posix())
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    assert prepublish.scan_repository(repo.root).findings == []
    assert opened and not any("data/private" in path for path in opened)


def test_output_and_report_never_contain_the_found_text(
    repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.write("notes.txt", f"{FAKE_KEY}\n{PERSONAL_MAIL}\n{PHONE}\n{USER_PATH}\n")
    repo.commit("add")
    report = tmp_path / "out" / "prepublish.md"
    code = prepublish.main(["--root", str(repo.root), "--report", str(report)])
    shown = capsys.readouterr().out
    recorded = report.read_text(encoding="utf-8")
    assert code == prepublish.EXIT_FOUND
    for text in (shown, recorded):
        for secret in (FAKE_KEY, PERSONAL_MAIL, PHONE, "fictional-user"):
            assert secret not in text
        assert "notes.txt:1" in text and "notes.txt:4" in text
    assert "これは実験的な参照仕様です。" in recorded and "見つかったものが 4件あります。" in recorded


def test_clean_run_exits_zero_and_records_zero(repo: Repo, tmp_path: Path) -> None:
    repo.write("README.md", "hello\n")
    repo.commit("first")
    report = tmp_path / "prepublish.md"
    args = ["--root", str(repo.root), "--report", str(report), "--lang", "ja"]
    assert prepublish.main(args) == prepublish.EXIT_OK
    recorded = report.read_text(encoding="utf-8")
    assert "見つかったものは 0件です。" in recorded and "2段目（名前の一覧と作者名）は実行していません" in recorded


def test_names_are_found_everywhere_but_never_shown(
    repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    names = tmp_path / "names.txt"
    names.write_text(f"# 探す名前\n\n{NAME}\n", encoding="utf-8")
    repo.write("docs/memo.md", f"担当: {NAME.upper()}\n")
    repo.write(f"notes/{NAME}.txt", "x\n")
    repo.commit(f"{NAME} さんの指摘を反映", author=NAME)
    entries = prepublish.load_names(names)
    assert entries == [(3, NAME)]

    result = prepublish.scan_names(repo.root, entries, MAINTAINER)
    kinds = {(f.category, f.where) for f in result.findings}
    assert kinds == {
        ("name_list", "file"),
        ("name_list", "path"),
        ("name_list", "commit_message"),
        ("name_list", "commit_author"),
        ("author", "commit_author"),
    }
    assert all(f.list_line == 3 for f in result.findings if f.category == "name_list")

    report = tmp_path / "prepublish.md"
    args = ["--root", str(repo.root), "--names", str(names), "--author", MAINTAINER]
    assert prepublish.main([*args, "--report", str(report)]) == prepublish.EXIT_FOUND
    for text in (capsys.readouterr().out, report.read_text(encoding="utf-8")):
        assert NAME.casefold() not in text.casefold()
        assert f"notes/{prepublish.MASK}.txt" in text


def test_name_list_problems_are_errors(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo.write("a.txt", "x\n")
    repo.commit("first")
    base = ["--root", str(repo.root), "--no-report"]
    assert prepublish.main([*base, "--names", str(tmp_path / "none.txt")]) == prepublish.EXIT_ERROR
    empty = tmp_path / "empty.txt"
    empty.write_text("# コメントだけ\n", encoding="utf-8")
    assert prepublish.main([*base, "--names", str(empty)]) == prepublish.EXIT_ERROR

    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert prepublish.main(["--root", str(plain), "--no-report"]) == prepublish.EXIT_ERROR


def test_path_and_email_rules() -> None:
    assert prepublish.is_private_path(".env")
    assert prepublish.is_private_path("config/.env.production")
    assert prepublish.is_private_path("data/private/list.csv")
    assert prepublish.is_private_path("keys/server.pem")
    assert not prepublish.is_private_path(".env.example")
    assert not prepublish.is_private_path("docs/private-notes.md")
    assert prepublish._email_allowed("a" + "@" + "sub.example.com")
    assert prepublish._email_allowed("a" + "@" + "agent.invalid")
    assert not prepublish._email_allowed("a" + "@" + "example.co.jp")


def test_names_match_across_full_and_half_width(repo: Repo, tmp_path: Path) -> None:
    names = tmp_path / "names.txt"
    names.write_text(NAME_FULL_WIDTH + "\n", encoding="utf-8")
    repo.write("docs/memo.md", f"担当: {NAME}\n")
    repo.write(f"notes/{NAME}.txt", "x\n")
    repo.commit("add")
    entries = prepublish.load_names(names)
    result = prepublish.scan_names(repo.root, entries)
    assert {(f.category, f.where, f.path) for f in result.findings} == {
        ("name_list", "file", "docs/memo.md"),
        ("name_list", "path", f"notes/{NAME}.txt"),
    }
    masked = prepublish.mask_findings(result.findings, entries)
    assert all(NAME.casefold() not in f.path.casefold() for f in masked)


def test_name_list_must_be_utf8(repo: Repo, tmp_path: Path) -> None:
    repo.write("a.txt", "x\n")
    repo.commit("first")
    names = tmp_path / "names.txt"
    names.write_bytes("架空の名前".encode("cp932"))
    args = ["--root", str(repo.root), "--names", str(names), "--no-report"]
    assert prepublish.main(args) == prepublish.EXIT_ERROR


def test_staged_files_without_any_commit_can_be_checked(repo: Repo, tmp_path: Path) -> None:
    """公開用の置き場のように、登録しただけでコミットのない置き場も調べられること。"""
    repo.write("README.md", "hello\n")
    repo.write("notes.txt", f"key = {FAKE_KEY}\n")
    repo.git("add", "-A")
    result = prepublish.scan_repository(repo.root)
    assert {(f.category, f.where, f.path) for f in result.findings} == {("secret", "file", "notes.txt")}
    assert (result.files, result.history_blobs, result.commits) == (2, 0, 0)
    assert prepublish.head_state(repo.root) == ("-", True)
    report = tmp_path / "prepublish.md"
    assert prepublish.main(["--root", str(repo.root), "--report", str(report)]) == prepublish.EXIT_FOUND
