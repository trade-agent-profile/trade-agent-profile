"""公開前の検査：秘密情報・実データ・個人の情報が、公開するものに入っていないかを機械的に調べる。

2段に分けてある。

- 1段目 scan_repository()：名前の一覧がなくても分かるものを探す。対象は、git で管理している
  今のファイル、git の履歴にだけ残っているファイルの版、コミットの説明文。総合チェック
  （scripts/check.py）からも実行する。
- 2段目 scan_names()：利用者が用意した「探す名前の一覧」の語と、コミットの作者名を調べる。
  一覧は利用者だけが読む場所（data/private/）に置くので、2段目は利用者が自分で実行する。

見つかった文字列そのものは、画面にも記録にも出さない（種類・件数・場所だけを出す）。
2段目では、場所の表示に含まれる一覧の語も伏せる。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from trade_agent_profile import i18n
from trade_agent_profile.cli import setup_stdio
from trade_agent_profile.paths import format_path

STAGE1_CATEGORIES = (
    "secret",
    "tracked_private",
    "email",
    "phone",
    "user_path",
    "sample_marker",
    "document_file",
)
STAGE2_CATEGORIES = ("name_list", "author")
EXIT_OK, EXIT_FOUND, EXIT_ERROR = 0, 1, 2
MASK = "＊＊＊"

# 鍵やトークンの形。よく使われるサービスのもので、ほかの文字列に誤って当たりにくい形だけを選んだ。
_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd)"
        r"\b\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"
    ),
]
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# 例示用に取っておかれた名前（RFC 2606、RFC 6761）と、コミットの共同作者の決まった書き方は除く
_EMAIL_ALLOWED_DOMAINS = ("example.com", "example.net", "example.org")
_EMAIL_ALLOWED_SUFFIXES = (".example", ".invalid", ".test", ".localhost")
_EMAIL_ALLOWED_ADDRESSES = frozenset({"noreply@anthropic.com"})
_PHONE_PATTERNS = [
    re.compile(r"(?<![\d-])0\d{1,4}-\d{1,4}-\d{3,4}(?![\d-])"),
    re.compile(r"(?<![\d+])\+(?:81|86)[ -]?\d{1,4}[ -]?\d{1,4}[ -]?\d{3,4}(?!\d)"),
]
# 利用者のフォルダ。＜名前＞ や %USERPROFILE% のように伏せた書き方は除く
_USER_PATH_PATTERNS = [
    re.compile(r"(?i)\b[a-z]:[\\/]+users[\\/]+(?![<＜{%$\[(])[^\\/\s\"'<>|:*?]+"),
    re.compile(r"(?<![\w.~-])/(?:Users|home)/(?![<＜{%$\[(])[A-Za-z0-9._-]+"),
]
_PRIVATE_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".keystore", ".sqlite3", ".db"})
_KEY_FILE_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")
_DOCUMENT_SUFFIXES = frozenset(
    {
        ".pdf",
        ".xls",
        ".xlsx",
        ".xlsm",
        ".csv",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tif",
        ".tiff",
        ".heic",
        ".webp",
        ".zip",
        ".msg",
        ".eml",
    }
)
# 見本の当事者名と品名に入れる「架空の印」（CONTRIBUTING.md の「入れてはいけないもの」）
_NAME_MARKERS = ("sample", "example", "demo")
_DESCRIPTION_MARKER = "(sample"


class GitError(RuntimeError):
    """git の命令が失敗した（git の管理下のフォルダではない、など）。"""


@dataclass(frozen=True)
class Finding:
    """見つかったもの1件。文字列そのものは持たず、種類と場所だけを持つ。"""

    category: str
    where: str  # file / history / commit_message / commit_author / path / ref
    path: str = ""
    line: int | None = None
    blob: str = ""  # 履歴の中のファイルの版（先頭7文字）
    commit: str = ""
    field_path: str = ""  # 見本の JSON の項目の道筋
    list_line: int | None = None  # 名前の一覧の何行目の語か


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    files: int = 0
    history_blobs: int = 0
    commits: int = 0
    names_checked: int | None = None  # None は「2段目を実行していない」


# ---- git から読む ----


def _git(root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    done = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=root,
        input=stdin,
        capture_output=True,
        check=False,
    )
    if done.returncode != 0:
        raise GitError(done.stderr.decode("utf-8", "replace").strip())
    return done.stdout


def _tracked_paths(root: Path) -> list[str]:
    return [
        path for path in _git(root, "ls-files", "-z").decode("utf-8", "replace").split("\0") if path
    ]


def _worktree_blob_ids(root: Path, paths: list[str]) -> set[str]:
    """今のファイルを git に入れたときの版の識別子（履歴と重ねて調べないため）。"""
    existing = [path for path in paths if (root / path).is_file()]
    if not existing:
        return set()
    listed = ("\n".join(existing) + "\n").encode("utf-8")
    return set(_git(root, "hash-object", "--stdin-paths", stdin=listed).decode().split())


def _history_blobs(root: Path) -> dict[str, str]:
    """すべての枝とタグから届くファイルの版：識別子 → そのファイルの道筋。"""
    if not _has_history(root):
        return {}
    listing = _git(root, "rev-list", "--all", "--objects")
    checked = _git(
        root, "cat-file", "--batch-check=%(objectname) %(objecttype) %(rest)", stdin=listing
    )
    blobs: dict[str, str] = {}
    for line in checked.decode("utf-8", "replace").splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[1] == "blob":
            blobs.setdefault(parts[0], parts[2])
    return blobs


def _history_paths(root: Path) -> set[str]:
    """これまでに一度でも git に入ったファイルの道筋。"""
    if not _has_history(root):
        return set()
    out = _git(root, "log", "--all", "--name-only", "--no-renames", "--format=")
    return {line for line in out.decode("utf-8", "replace").splitlines() if line}


def _read_blobs(root: Path, ids: list[str]) -> Iterator[tuple[str, bytes]]:
    if not ids:
        return
    out = _git(root, "cat-file", "--batch", stdin=("\n".join(ids) + "\n").encode())
    position = 0
    while position < len(out):
        header_end = out.index(b"\n", position)
        object_id, _kind, size = out[position:header_end].decode().split(" ")
        start = header_end + 1
        end = start + int(size)
        yield object_id, out[start:end]
        position = end + 1


def _commit_messages(root: Path) -> list[tuple[str, str]]:
    if not _has_history(root):
        return []
    out = _git(root, "log", "--all", "--format=%h%x1f%B%x1e")
    messages = []
    for chunk in out.decode("utf-8", "replace").split("\x1e"):
        chunk = chunk.strip("\n")
        if chunk:
            short, _, body = chunk.partition("\x1f")
            messages.append((short, body))
    return messages


def _commit_people(root: Path) -> list[tuple[str, list[str]]]:
    """コミットごとの作者名・作者のメール・記録者名・記録者のメール（2段目だけで使う）。"""
    if not _has_history(root):
        return []
    out = _git(root, "log", "--all", "--format=%h%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1e")
    people = []
    for chunk in out.decode("utf-8", "replace").split("\x1e"):
        chunk = chunk.strip("\n")
        if chunk:
            short, *fields = chunk.split("\x1f")
            people.append((short, fields))
    return people


def _refs(root: Path) -> list[str]:
    out = _git(root, "for-each-ref", "--format=%(refname)")
    return [line for line in out.decode("utf-8", "replace").splitlines() if line]


def _has_history(root: Path) -> bool:
    """枝やタグが1つでもあるか（git init して登録しただけの置き場には、まだ履歴がない）。"""
    return bool(_git(root, "for-each-ref", "--count=1").strip())


def head_state(root: Path) -> tuple[str, bool]:
    """(今のコミットの短い識別子。まだなければ "-", まだコミットしていない変更があるか)"""
    dirty = bool(_git(root, "status", "--porcelain").strip())
    if not _has_history(root):
        return "-", dirty
    return _git(root, "rev-parse", "--short", "HEAD").decode().strip(), dirty


# ---- 1段目 ----


def is_private_path(path: str) -> bool:
    """git に入れてはいけない種類のファイルか（.env、data/private/、鍵のファイルなど）。"""
    posix = PurePosixPath(path)
    name = posix.name
    if posix.parts[:2] == ("data", "private"):
        return True
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True
    if posix.suffix.lower() in _PRIVATE_SUFFIXES:
        return True
    return name.startswith(_KEY_FILE_PREFIXES)


def is_document_file(path: str) -> bool:
    """書類や画像のファイルか（実データが写っていないかを人が確かめる）。"""
    return PurePosixPath(path).suffix.lower() in _DOCUMENT_SUFFIXES


def _email_allowed(address: str) -> bool:
    lowered = address.lower()
    if lowered in _EMAIL_ALLOWED_ADDRESSES:
        return True
    domain = lowered.rsplit("@", 1)[1]
    if domain.endswith(_EMAIL_ALLOWED_SUFFIXES):
        return True
    return any(domain == base or domain.endswith("." + base) for base in _EMAIL_ALLOWED_DOMAINS)


def scan_text(text: str) -> Iterator[tuple[str, int]]:
    """文章の中から、1段目で探す形を探す。(種類, 行番号) を返す。"""
    for number, line in enumerate(text.splitlines(), start=1):
        if any(pattern.search(line) for pattern in _SECRET_PATTERNS):
            yield "secret", number
        if any(not _email_allowed(match.group(0)) for match in _EMAIL.finditer(line)):
            yield "email", number
        if any(pattern.search(line) for pattern in _PHONE_PATTERNS):
            yield "phone", number
        if any(pattern.search(line) for pattern in _USER_PATH_PATTERNS):
            yield "user_path", number


def _is_sample_json(path: str) -> bool:
    posix = PurePosixPath(path)
    if posix.suffix != ".json" or not posix.parts:
        return False
    top = posix.parts[0]
    return (
        top in ("samples", "conformance")
        or (top == "dist" and "samples" in posix.parts)
        or path.startswith("src/trade_agent_profile/data/")
    )


def sample_marker_problems(data: Any) -> Iterator[str]:
    """見本の当事者名（name）と品名（description）に、架空の印がない場所の道筋を返す。"""

    def walk(node: Any, parts: list[str | int]) -> Iterator[str]:
        if isinstance(node, dict):
            for key, value in node.items():
                here = [*parts, key]
                if isinstance(value, str):
                    lowered = value.casefold()
                    if key == "name" and not any(mark in lowered for mark in _NAME_MARKERS):
                        yield format_path(here)
                    elif key == "description" and _DESCRIPTION_MARKER not in lowered:
                        yield format_path(here)
                else:
                    yield from walk(value, here)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from walk(value, [*parts, index])

    yield from walk(data, [])


def _is_binary(data: bytes) -> bool:
    return b"\0" in data[:8000]


def _dedupe(findings: Iterable[Finding]) -> list[Finding]:
    return list(dict.fromkeys(findings))


def scan_repository(root: Path) -> ScanResult:
    """1段目：名前の一覧がなくても分かるものを探す。"""
    root = Path(root)
    tracked = _tracked_paths(root)
    findings: list[Finding] = []
    files = 0
    for path in tracked:
        if is_private_path(path):
            findings.append(Finding("tracked_private", "file", path))
        if is_document_file(path):
            findings.append(Finding("document_file", "file", path))
        full = root / path
        if not full.is_file():
            continue
        data = full.read_bytes()
        files += 1
        if _is_binary(data):
            continue
        text = data.decode("utf-8", "replace")
        findings.extend(Finding(kind, "file", path, line=line) for kind, line in scan_text(text))
        if _is_sample_json(path):
            try:
                parsed = json.loads(text)
            except ValueError:
                continue
            findings.extend(
                Finding("sample_marker", "file", path, field_path=where)
                for where in sample_marker_problems(parsed)
            )

    tracked_set = set(tracked)
    for path in sorted(_history_paths(root) - tracked_set):
        if is_private_path(path):
            findings.append(Finding("tracked_private", "history", path))
        if is_document_file(path):
            findings.append(Finding("document_file", "history", path))

    current = _worktree_blob_ids(root, tracked)
    history = {oid: path for oid, path in _history_blobs(root).items() if oid not in current}
    for oid, data in _read_blobs(root, sorted(history, key=lambda oid: (history[oid], oid))):
        if _is_binary(data):
            continue
        findings.extend(
            Finding(kind, "history", history[oid], line=line, blob=oid[:7])
            for kind, line in scan_text(data.decode("utf-8", "replace"))
        )

    messages = _commit_messages(root)
    for short, body in messages:
        findings.extend(
            Finding(kind, "commit_message", commit=short, line=line)
            for kind, line in scan_text(body)
        )
    return ScanResult(_dedupe(findings), files, len(history), len(messages))


# ---- 2段目 ----


def _fold(text: str) -> str:
    """大文字と小文字、全角と半角（文字と空白）の違いをならす。"""
    return unicodedata.normalize("NFKC", text).casefold()


def load_names(path: Path) -> list[tuple[int, str]]:
    """名前の一覧を読む。1行に1語。空の行と # で始まる行は飛ばす。(行番号, 語) を返す。

    UTF-8 で読めないときは UnicodeDecodeError を出す（BOM はあってもなくてもよい）。
    """
    entries = []
    for number, raw in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        word = raw.strip()
        if word and not word.startswith("#"):
            entries.append((number, word))
    return entries


def scan_names(
    root: Path, entries: list[tuple[int, str]], expected_author: str | None = None
) -> ScanResult:
    """2段目：一覧の語と、コミットの作者名を調べる。大文字と小文字、全角と半角は区別しない。"""
    root = Path(root)
    words = [(number, _fold(word)) for number, word in entries]

    def hits(text: str) -> list[int]:
        folded = _fold(text)
        return [number for number, word in words if word in folded]

    def in_lines(text: str, make: Any) -> Iterator[Finding]:
        for line_no, line in enumerate(text.splitlines(), start=1):
            for list_line in hits(line):
                yield make(line_no, list_line)

    findings: list[Finding] = []
    tracked = _tracked_paths(root)
    files = 0
    for path in tracked:
        findings.extend(Finding("name_list", "path", path, list_line=n) for n in hits(path))
        full = root / path
        if full.is_file():
            files += 1
            text = full.read_bytes().decode("utf-8", "replace")
            findings.extend(
                in_lines(
                    text, lambda ln, n, p=path: Finding("name_list", "file", p, ln, list_line=n)
                )
            )
    for path in sorted(_history_paths(root) - set(tracked)):
        findings.extend(Finding("name_list", "path", path, list_line=n) for n in hits(path))

    current = _worktree_blob_ids(root, tracked)
    history = {oid: path for oid, path in _history_blobs(root).items() if oid not in current}
    for oid, data in _read_blobs(root, sorted(history, key=lambda oid: (history[oid], oid))):
        text = data.decode("utf-8", "replace")
        findings.extend(
            in_lines(
                text,
                lambda ln, n, p=history[oid], b=oid[:7]: Finding(
                    "name_list", "history", p, ln, blob=b, list_line=n
                ),
            )
        )

    messages = _commit_messages(root)
    for short, body in messages:
        findings.extend(
            in_lines(
                body,
                lambda ln, n, c=short: Finding(
                    "name_list", "commit_message", commit=c, line=ln, list_line=n
                ),
            )
        )
    for short, people in _commit_people(root):
        for list_line in sorted({n for value in people for n in hits(value)}):
            findings.append(
                Finding("name_list", "commit_author", commit=short, list_line=list_line)
            )
        if expected_author is not None and (
            people[0] != expected_author or people[2] != expected_author
        ):
            findings.append(Finding("author", "commit_author", commit=short))
    for ref in _refs(root):
        findings.extend(Finding("name_list", "ref", ref, list_line=n) for n in hits(ref))
    return ScanResult(_dedupe(findings), files, len(history), len(messages), len(entries))


def mask_findings(findings: list[Finding], entries: list[tuple[int, str]]) -> list[Finding]:
    """場所の表示（ファイルの道筋や枝の名前）に含まれる一覧の語を伏せる。"""
    patterns = [re.compile(re.escape(word), re.IGNORECASE) for _, word in entries]
    folded = [_fold(word) for _, word in entries]
    masked = []
    for finding in findings:
        path = finding.path
        for pattern in patterns:
            path = pattern.sub(MASK, path)
        if any(word in _fold(path) for word in folded):
            path = MASK  # 全角と半角の違いなどで語の部分だけを伏せられないときは、道筋ごと伏せる
        masked.append(replace(finding, path=path))
    return masked


# ---- 表示と記録 ----


def _texts(lang: str) -> dict[str, Any]:
    return i18n.catalog(lang)["prepublish"]


def describe(finding: Finding, lang: str) -> str:
    """見つかった場所を、人が読む形にする。"""
    where = _texts(lang)["where"]
    base = f"{finding.path}:{finding.line}" if finding.line else finding.path
    if finding.where == "file":
        text = base
    elif finding.where == "history":
        key = "history_blob" if finding.blob else "history_path"
        text = i18n.render(where[key], {"location": base, "blob": finding.blob})
    else:
        text = i18n.render(
            where[finding.where],
            {"path": finding.path, "line": finding.line, "commit": finding.commit},
        )
    if finding.field_path:
        text += i18n.render(where["field"], {"field": finding.field_path})
    if finding.list_line is not None:
        text += i18n.render(where["list_line"], {"line": finding.list_line})
    return text


def _categories(result: ScanResult) -> tuple[str, ...]:
    return STAGE1_CATEGORIES + (STAGE2_CATEGORIES if result.names_checked is not None else ())


def _label(lang: str, category: str, author: str | None) -> str:
    return i18n.render(_texts(lang)["categories"][category], {"author": author or "-"})


def _verdict(result: ScanResult, lang: str) -> str:
    texts = _texts(lang)
    if result.findings:
        return i18n.render(texts["found"], {"count": len(result.findings)})
    return texts["all_clear"]


def _scope_lines(
    result: ScanResult, lang: str, commit: str, dirty: bool, author: str | None
) -> list[str]:
    texts = _texts(lang)
    lines = [
        i18n.render(texts["commit"], {"commit": commit, "dirty": texts["dirty"] if dirty else ""}),
        i18n.render(
            texts["scope"],
            {"files": result.files, "history": result.history_blobs, "commits": result.commits},
        ),
    ]
    if result.names_checked is None:
        lines.append(texts["stage2_skipped"])
    else:
        lines.append(i18n.render(texts["names_scope"], {"count": result.names_checked}))
        if author is not None:
            lines.append(i18n.render(texts["author_scope"], {"author": author}))
    return lines


def _grouped(result: ScanResult) -> dict[str, list[Finding]]:
    groups: dict[str, list[Finding]] = {}
    for finding in result.findings:
        groups.setdefault(finding.category, []).append(finding)
    return groups


def _needs_history_note(result: ScanResult) -> bool:
    return any(
        finding.where in ("history", "commit_message", "commit_author")
        or finding.category == "author"
        for finding in result.findings
    )


def format_text(
    result: ScanResult,
    langs: tuple[str, ...],
    commit: str,
    dirty: bool,
    author: str | None = None,
    quiet: bool = False,
) -> str:
    """画面に出す文章。quiet のときは、見つかったものと結論だけ。"""
    blocks = []
    groups = _grouped(result)
    for lang in langs:
        texts = _texts(lang)
        lines: list[str] = []
        if not quiet:
            ui = i18n.catalog(lang)["ui"]
            lines += [ui["notice"], ui["judge"], "", texts["title"]]
            lines += _scope_lines(result, lang, commit, dirty, author)
            lines.append("")
            for category in _categories(result):
                count = len(groups.get(category, []))
                label = _label(lang, category, author)
                lines.append(i18n.render(texts["count_line"], {"label": label, "count": count}))
            lines.append("")
        for category, items in groups.items():
            label = _label(lang, category, author)
            lines.append(i18n.render(texts["group"], {"label": label, "count": len(items)}))
            lines += [f"  - {describe(finding, lang)}" for finding in items]
            lines.append(f"  → {texts['fixes'][category]}")
        if _needs_history_note(result):
            lines.append(texts["history_note"])
        lines.append(_verdict(result, lang))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def format_report(
    result: ScanResult,
    langs: tuple[str, ...],
    commit: str,
    dirty: bool,
    when: datetime,
    author: str | None = None,
) -> str:
    """reports/ に残す記録（Markdown）。見つかった文字列そのものは書かない。"""
    sections = []
    groups = _grouped(result)
    for lang in langs:
        texts = _texts(lang)
        ui = i18n.catalog(lang)["ui"]
        lines = [f"# {texts['report_title']}", "", f"> {ui['notice']}", f"> {ui['judge']}", ""]
        lines.append(
            f"- {i18n.render(texts['when'], {'when': when.isoformat(timespec='seconds')})}"
        )
        lines += [f"- {line}" for line in _scope_lines(result, lang, commit, dirty, author)]
        lines += ["", f"| {texts['table_category']} | {texts['table_count']} |", "|---|---|"]
        for category in _categories(result):
            count = len(groups.get(category, []))
            lines.append(f"| {_label(lang, category, author)} | {count} |")
        lines += ["", f"## {texts['report_places']}", ""]
        if not result.findings:
            lines.append(texts["none"])
        for category, items in groups.items():
            lines.append(f"### {_label(lang, category, author)}")
            lines += [f"- {describe(finding, lang)}" for finding in items]
            lines += [f"- → {texts['fixes'][category]}", ""]
        if _needs_history_note(result):
            lines += ["", texts["history_note"]]
        lines += ["", _verdict(result, lang)]
        sections.append("\n".join(lines))
    return "\n\n".join(sections).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    parser = argparse.ArgumentParser(description="公開前の検査 / Pre-publication check")
    parser.add_argument("--root", default=".", help="調べる git のフォルダ / git folder to check")
    parser.add_argument(
        "--names",
        metavar="FILE",
        help=(
            "2段目：探す名前の一覧（1行に1語）。一覧を用意した人が自分で実行する / "
            "stage 2: file listing names to look for (one per line); run it yourself"
        ),
    )
    parser.add_argument(
        "--author",
        metavar="NAME",
        help="2段目：コミットの作者名として正しい名前 / stage 2: the expected commit author name",
    )
    parser.add_argument(
        "--report",
        metavar="FILE",
        help="記録の書き先（既定は reports/prepublish.md） / record file (default: reports/prepublish.md)",
    )
    parser.add_argument(
        "--no-report", action="store_true", help="記録を書かない / do not write a record"
    )
    parser.add_argument("--lang", choices=("both", "ja", "en"), default="both")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="見つかったものと結論だけを出す / print only findings and the verdict",
    )
    args = parser.parse_args(argv)
    langs = i18n.LANGS if args.lang == "both" else (args.lang,)
    root = Path(args.root).resolve()

    def error(key: str, **params: object) -> int:
        for lang in langs:
            print(i18n.render(_texts(lang)[key], params), file=sys.stderr)
        return EXIT_ERROR

    entries: list[tuple[int, str]] = []
    if args.names:
        names_path = Path(args.names)
        if not names_path.is_file():
            return error("names_missing", path=args.names)
        try:
            entries = load_names(names_path)
        except UnicodeDecodeError:
            return error("names_encoding", path=args.names)
        if not entries:
            return error("names_empty", path=args.names)
    try:
        result = scan_repository(root)
        if args.names or args.author is not None:
            stage2 = scan_names(root, entries, args.author)
            result = ScanResult(
                mask_findings(result.findings + stage2.findings, entries),
                result.files,
                result.history_blobs,
                result.commits,
                stage2.names_checked,
            )
        commit, dirty = head_state(root)
    except GitError:
        return error("no_git", path=str(root))

    print(format_text(result, langs, commit, dirty, args.author, args.quiet))
    if not args.no_report:
        report = Path(args.report) if args.report else root / "reports" / "prepublish.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        when = datetime.now().astimezone()
        text = format_report(result, langs, commit, dirty, when, args.author)
        report.write_text(text, encoding="utf-8", newline="\n")
        for lang in langs:
            print(i18n.render(_texts(lang)["report_written"], {"path": str(report)}))
    return EXIT_FOUND if result.findings else EXIT_OK
