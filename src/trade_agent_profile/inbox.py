"""受け付けの流れ：二重処理の防止 → 検証 → 役割ごとの処理 → 返事の組み立て。

通信の方式には依存しない。M3 では、この流れをそのまま A2A の通信に載せる。
A2A の用語との対応（節番号は A2A 仕様 1.0.0）：
- 受け付けた1件の仕事が「タスク」（4.1.1）。識別子は受け手が振る（3.4.2）。
- 仕事の結果（見積、ブッキング確認、申告の下書き）は Artifact で返す（3.7、4.1.7）。
- 入力を求める・断る・誤りを知らせる封筒は、タスクの状態に添える（3.7、4.1.2）。
- 同じ message_id の再送は、処理をやり直さず、最初の結果を返す（3.3.1）。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from . import i18n
from .issues import Issue
from .messages import UUID_RE, digest, new_message, validate_message
from .profile import FAILED, INPUT_REQUIRED, REJECTED, RESULT_TYPES, TERMINAL_STATES

_VERSION_CODES = ("PROFILE_UNKNOWN", "PROFILE_VERSION_UNSUPPORTED")


class TaskNotFoundError(LookupError):
    """指定されたタスクがない（A2A の TaskNotFoundError にあたる。3.4.2）。"""


class TaskClosedError(RuntimeError):
    """終わったタスクには続きを送れない（A2A の UnsupportedOperationError にあたる。3.1.1）。"""


@dataclass
class Reply:
    """役割ごとの処理が返すもの。封筒にするのは受け付けの側で行う。"""

    state: str
    message_type: str | None = None
    payload: dict[str, Any] | None = None
    role: str | None = None  # 返事を出す立場（例 forwarder、customs_broker）


@dataclass
class Outcome:
    """1件のメッセージを受け付けた結果。"""

    task_id: str
    state: str
    at: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    status_message: dict[str, Any] | None = None
    duplicate: bool = False


def error_payload(code: str, issues: Iterable[Issue] = ()) -> dict[str, Any]:
    """error メッセージの中身を作る。文は日本語と英語の両方を入れる。"""
    return {
        "code": code,
        "text": {lang: i18n.catalog(lang)["message_errors"][code] for lang in i18n.LANGS},
        "issues": [{"code": issue.code, "path": issue.path} for issue in issues],
    }


class InboxStore:
    """処理済みの message_id と、その結果の控え（SQLite）。"""

    def __init__(self, path: str = ":memory:") -> None:
        # 通信に載せると、作ったのとは別のスレッドから使われる。使うのは1度に1か所だけ
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS processed ("
            "message_id TEXT PRIMARY KEY, digest TEXT NOT NULL, "
            "received_at TEXT NOT NULL, outcome TEXT NOT NULL)"
        )
        self._db.commit()

    def get(self, message_id: str) -> tuple[str, Outcome] | None:
        row = self._db.execute(
            "SELECT digest, outcome FROM processed WHERE message_id = ?", (message_id,)
        ).fetchone()
        if row is None:
            return None
        return row[0], Outcome(**json.loads(row[1]))

    def put(self, message_id: str, fingerprint: str, outcome: Outcome) -> None:
        text = json.dumps(asdict(outcome), ensure_ascii=False)
        self._db.execute(
            "INSERT INTO processed (message_id, digest, received_at, outcome) VALUES (?, ?, ?, ?)",
            (message_id, fingerprint, outcome.at, text),
        )
        self._db.commit()

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM processed").fetchone()[0]

    def close(self) -> None:
        self._db.close()


class Receiver:
    """メッセージを受け付ける側の共通の流れ。"""

    def __init__(
        self,
        handler: Callable[[dict[str, Any]], Reply],
        *,
        sender: dict[str, str],
        store: InboxStore,
        clock: Callable[[], str],
        new_id: Callable[[], str],
    ) -> None:
        self.handler = handler
        self.sender = sender
        self.store = store
        self.clock = clock
        self.new_id = new_id
        self.tasks: dict[str, str] = {}  # タスクの識別子 → いまの状態

    def receive(
        self, envelope: Any, task_id: str | None = None, *, assigned_task_id: str | None = None
    ) -> Outcome:
        """1件受け付ける。

        task_id は、入力待ちのタスクに続きを送るときだけ渡す。
        assigned_task_id は、新しいタスクの識別子を呼び出し側（A2A の部品）が
        すでに決めているときに渡す。渡さなければ、ここで振る。
        """
        message_id = envelope.get("message_id") if isinstance(envelope, dict) else None
        usable = isinstance(message_id, str) and bool(UUID_RE.match(message_id))
        fingerprint = digest(envelope) if usable else ""

        if usable:
            stored = self.store.get(message_id)
            if stored is not None:
                old_fingerprint, outcome = stored
                if old_fingerprint == fingerprint:
                    return replace(outcome, duplicate=True)  # 処理はやり直さない
                reply = Reply(REJECTED, "error", error_payload("MESSAGE_ID_REUSED"))
                return self._finish(self._open_task(None, assigned_task_id), envelope, reply, None)

        task = self._open_task(task_id, assigned_task_id)
        result = validate_message(envelope)
        if result.valid:
            try:
                reply = self.handler(envelope)
            except Exception:  # 想定外の失敗は、中の事情を出さずに「失敗」として返す
                reply = Reply(FAILED, "error", error_payload("INTERNAL_ERROR"))
        elif result.errors[0].code in _VERSION_CODES:
            reply = Reply(REJECTED, "error", error_payload(result.errors[0].code, result.errors))
        else:
            reply = Reply(
                INPUT_REQUIRED, "error", error_payload("VALIDATION_FAILED", result.errors)
            )
        return self._finish(task, envelope, reply, (message_id, fingerprint) if usable else None)

    def processed(self, envelope: Any) -> Outcome | None:
        """同じ message_id・同じ中身のメッセージをすでに受け付けていれば、そのときの結果を返す。

        通信の部品が、タスクを探す前に再送を見分けるために使う。受け付けていなければ None。
        """
        message_id = envelope.get("message_id") if isinstance(envelope, dict) else None
        if not (isinstance(message_id, str) and UUID_RE.match(message_id)):
            return None
        stored = self.store.get(message_id)
        if stored is None or stored[0] != digest(envelope):
            return None
        return replace(stored[1], duplicate=True)

    def adopt(self, task_id: str, state: str) -> None:
        """呼び出し側が振ったタスクの識別子を、状態と一緒に覚える。

        再送に、控えてある結果を新しいタスクとして返したときに使う。
        """
        self.tasks[task_id] = state

    def _open_task(self, task_id: str | None, assigned: str | None = None) -> str:
        if task_id is None:
            return assigned or self.new_id()
        if task_id not in self.tasks:
            raise TaskNotFoundError(task_id)
        if self.tasks[task_id] in TERMINAL_STATES:
            raise TaskClosedError(task_id)
        return task_id

    def _finish(
        self, task: str, envelope: Any, reply: Reply, remember: tuple[str, str] | None
    ) -> Outcome:
        now = self.clock()
        outcome = Outcome(task, reply.state, now)
        if reply.message_type is not None:
            source = envelope if isinstance(envelope, dict) else {}
            correlation = source.get("correlation_id")
            if not (isinstance(correlation, str) and UUID_RE.match(correlation)):
                correlation = self.new_id()
            answered = source.get("message_id")
            if not (isinstance(answered, str) and UUID_RE.match(answered)):
                answered = None
            message = new_message(
                reply.message_type,
                reply.payload or {},
                sender=dict(self.sender, role=reply.role or self.sender["role"]),
                correlation_id=correlation,
                sent_at=now,
                message_id=self.new_id(),
                in_reply_to=answered,
            )
            if reply.message_type in RESULT_TYPES:
                outcome.artifacts.append(message)
            else:
                outcome.status_message = message
        self.tasks[task] = reply.state
        if remember is not None:
            self.store.put(remember[0], remember[1], outcome)
        return outcome
