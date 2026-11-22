"""適合テスト：ある実装が、このプロファイルの決まりどおりに答えるかを確かめる。

conformance/cases/ の各ファイルが1件のテストで、送るもの（入力）と期待する答え
（期待出力）の組になっている。相手とは A2A で通信する。

手順の書き方：
- "send"      封筒を送る（"continue": 番号 を付けると、その手順のタスクの続きとして送る）
- "resend"    前の手順で送った封筒を、そのままもう一度送る
- "text"      封筒の代わりに、文字だけのメッセージを送る
- "card"      何も送らず、AgentCard の宣言を確かめる
- "without_extension"  プロファイルを使うと名乗らずに送る（A2A-Extensions ヘッダなし）
期待する答えは "expect" に書く。"state" と "reply"、または "error"（A2A のエラーの呼び名）。
答え方が2通り認められている手順では、"any_of" に並べ、どれか1つに合えば合格とする。

入力の中の決まった書き方：
- "$id:名前"   そのテストの中で同じ名前には同じ、新しい UUID に置き換える
- "$now"       いまの日時に置き換える
- "$reply:手順:道筋"  前の手順で返ってきた封筒の値に置き換える（例 "$reply:1:payload.quote_number"）
"""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from a2a.types import AgentCard
from a2a.utils.errors import A2A_ERROR_MAPPING, A2AError

from .a2a_agent import A2A_PROTOCOL_VERSION, A2ALink, card_summary
from .inbox import Outcome
from .messages import UUID_RE, validate_message
from .paths import parse_field_path, resolve
from .profile import PROFILE, PROFILE_URI, PROFILE_VERSION

_JST = timezone(timedelta(hours=9))
Problem = tuple[str, dict[str, Any]]  # 文言の鍵と、埋める値


@dataclass
class CaseResult:
    """1件のテストの結果。"""

    case_id: str
    title: dict[str, str]
    skipped: bool = False
    problems: list[Problem] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.skipped and not self.problems


def load_cases(folder: str | Path) -> list[dict[str, Any]]:
    """テストのファイルを、名前の順に読む。"""
    paths = sorted(Path(folder).glob("*.json"))
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def applies(case: dict[str, Any], accepts: list[str], required: bool = True) -> bool:
    """相手の AgentCard の宣言から、このテストが当てはまるかを決める。

    accepts は相手が引き受ける種類、required は拡張を必須（required: true）と
    宣言しているかどうか。
    """
    needs_ok = all(kind in accepts for kind in case.get("needs", []))
    refuses_ok = all(kind not in accepts for kind in case.get("refuses", []))
    required_ok = required or not case.get("extension_required", False)
    return needs_ok and refuses_ok and required_ok


def _error_name(error: A2AError) -> str:
    """A2A のエラーの呼び名（仕様の理由コード。例 EXTENSION_SUPPORT_REQUIRED）。"""
    mapping = A2A_ERROR_MAPPING.get(type(error))
    return mapping.reason if mapping is not None else type(error).__name__


class _Filler:
    """入力の中の決まった書き方を、実際の値に置き換える。"""

    def __init__(self) -> None:
        self.ids: dict[str, str] = {}
        self.replies: dict[int, Any] = {}

    def fill(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self.fill(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.fill(item) for item in value]
        if not isinstance(value, str) or not value.startswith("$"):
            return value
        if value == "$now":
            return datetime.now(_JST).isoformat(timespec="seconds")
        if value.startswith("$id:"):
            return self.ids.setdefault(value[4:], str(uuid.uuid4()))
        if value.startswith("$reply:"):
            _, step, path = value.split(":", 2)
            found, result = resolve(self.replies.get(int(step)), parse_field_path(path) or [])
            return result if found else None
        return value


def _reply_of(outcome: Outcome) -> tuple[str | None, Any]:
    """返ってきた封筒と、その置き場所（結果か、状態に添えたものか）。"""
    if outcome.artifacts:
        return "artifact", outcome.artifacts[0]
    if outcome.status_message is not None:
        return "status", outcome.status_message
    return None, None


def _includes(expected: Any, actual: Any, path: str) -> list[tuple[str, Any, Any]]:
    """期待する値が、実際の値に含まれているか。違う場所を並べる。"""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [(path, expected, actual)]
        found: list[tuple[str, Any, Any]] = []
        for key, item in expected.items():
            found += _includes(item, actual.get(key), f"{path}.{key}" if path else key)
        return found
    return [] if expected == actual else [(path, expected, actual)]


def _check_reply(
    step: int, expect: dict[str, Any], sent: Any, outcome: Outcome, first: dict[int, Any]
) -> list[Problem]:
    problems: list[Problem] = []
    place, reply = _reply_of(outcome)
    want = expect.get("reply")

    if outcome.state != expect["state"]:
        params = {"step": step, "actual": outcome.state, "expected": expect["state"]}
        problems.append(("p_state", params))
    if want is None:
        if "reply" in expect and reply is not None:
            problems.append(("p_reply_unexpected", {"step": step}))
    elif not isinstance(reply, dict):
        problems.append(("p_reply_missing", {"step": step, "expected": want["message_type"]}))
    else:
        if place != want["in"]:
            params = {"step": step, "actual": place, "expected": want["in"]}
            problems.append(("p_reply_place", params))
        if reply.get("message_type") != want["message_type"]:
            params = {
                "step": step,
                "actual": reply.get("message_type"),
                "expected": want["message_type"],
            }
            problems.append(("p_reply_type", params))
        result = validate_message(reply)
        if not result.valid:
            detail = ", ".join(f"[{issue.code}] {issue.path}" for issue in result.errors[:3])
            problems.append(("p_reply_invalid", {"step": step, "detail": detail}))
        if isinstance(sent, dict):
            sent_id = sent.get("message_id")
            if isinstance(sent_id, str) and UUID_RE.match(sent_id):
                if reply.get("in_reply_to") != sent_id:
                    problems.append(("p_in_reply_to", {"step": step}))
            thread = sent.get("correlation_id")
            if isinstance(thread, str) and UUID_RE.match(thread):
                if reply.get("correlation_id") != thread:
                    problems.append(("p_correlation", {"step": step}))
        payload = reply.get("payload") if isinstance(reply.get("payload"), dict) else {}
        if "code" in want and payload.get("code") != want["code"]:
            params = {"step": step, "actual": payload.get("code"), "expected": want["code"]}
            problems.append(("p_code", params))
        for issue in want.get("issues", []):
            if issue not in payload.get("issues", []):
                expected = f"[{issue['code']}] {issue['path']}"
                problems.append(("p_issue", {"step": step, "expected": expected}))
        for path, expected, actual in _includes(want.get("payload", {}), payload, "payload"):
            params = {"step": step, "path": path, "actual": actual, "expected": expected}
            problems.append(("p_payload", params))

    if "same_reply_as" in expect and reply != first.get(expect["same_reply_as"]):
        problems.append(("p_same_reply", {"step": step}))
    return problems


def check_card(card: AgentCard) -> list[Problem]:
    """AgentCard が、プロファイルを拡張として宣言しているか。"""
    summary = card_summary(card)
    problems: list[Problem] = []
    if not summary["declares_profile"]:
        return [("card_no_extension", {"uri": PROFILE_URI})]
    if summary["profile"] != PROFILE:
        problems.append(("card_profile", {"expected": PROFILE}))
    if PROFILE_VERSION not in summary["profile_versions"]:
        problems.append(("card_version", {"expected": PROFILE_VERSION}))
    versions = {interface["version"] for interface in summary["interfaces"]}
    if A2A_PROTOCOL_VERSION not in versions:
        problems.append(("card_interface", {"expected": A2A_PROTOCOL_VERSION}))
    return problems


def _judge(
    step: int,
    expect: dict[str, Any],
    sent: Any,
    happened: Outcome | A2AError,
    first: dict[int, Any],
) -> list[Problem]:
    """1つの期待と、実際に起きたこと（返ってきたタスクか、A2A のエラー）を比べる。"""
    want_error = expect.get("error")
    if isinstance(happened, A2AError):
        actual = _error_name(happened)
        if want_error is None:
            return [("p_error", {"step": step, "detail": f"{actual}: {happened}"[:200]})]
        if actual != want_error:
            return [("p_a2a_error", {"step": step, "actual": actual, "expected": want_error})]
        return []
    if want_error is not None:
        params = {"step": step, "expected": want_error, "state": happened.state}
        return [("p_a2a_error_missing", params)]
    return _check_reply(step, expect, sent, happened, first)


async def run_case(case: dict[str, Any], card: AgentCard, http: Any = None) -> CaseResult:
    """1件のテストを実行する。"""
    result = CaseResult(case["id"], case["title"])
    link = A2ALink(card, http)
    filler = _Filler()
    sent_by_step: dict[int, Any] = {}
    task_by_step: dict[int, str] = {}

    for number, step in enumerate(case["steps"], 1):
        if step.get("card"):
            result.problems += check_card(card)
            continue
        declare = not step.get("without_extension", False)
        happened: Outcome | A2AError
        try:
            task_id = task_by_step.get(step["continue"]) if "continue" in step else None
            if "text" in step:
                sent = None
                happened = await link.send(
                    None, task_id, text=step["text"], declare_extension=declare
                )
            else:
                if "resend" in step:
                    sent = copy.deepcopy(sent_by_step[step["resend"]])
                else:
                    sent = filler.fill(step["send"])
                happened = await link.send(sent, task_id, declare_extension=declare)
        except A2AError as error:  # A2A の決まったエラー。期待どおりなら合格
            happened = error
        except Exception as error:  # 通信の失敗も、テストの不合格として報告する
            detail = f"{type(error).__name__}: {error}"[:200]
            result.problems.append(("p_error", {"step": number, "detail": detail}))
            break
        if isinstance(happened, Outcome):
            sent_by_step[number] = sent
            task_by_step[number] = happened.task_id
            filler.replies[number] = _reply_of(happened)[1]

        # 答え方が2通り認められている手順は "any_of" に並べてある。どれか1つに合えば合格
        expect = step["expect"]
        choices = expect.get("any_of", [expect])
        found = min(
            (_judge(number, choice, sent, happened, filler.replies) for choice in choices), key=len
        )
        result.problems += found
        if found and isinstance(happened, A2AError):
            break  # 期待していないエラーのあとは、続きの手順を進められない
    return result


async def run_conformance(
    card: AgentCard,
    cases: list[dict[str, Any]],
    *,
    http: Any = None,
    accepts: list[str] | None = None,
) -> list[CaseResult]:
    """すべてのテストを実行する。相手の AgentCard の宣言と合わないテストは、対象外にする。"""
    summary = card_summary(card)
    if accepts is None:
        accepts = summary["accepts"]
    results = []
    for case in cases:
        if applies(case, accepts, summary["required"]):
            results.append(await run_case(case, card, http))
        else:
            results.append(CaseResult(case["id"], case["title"], skipped=True))
    return results
