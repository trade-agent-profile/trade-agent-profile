"""A2A の通信に載せる部分。公式の a2a-sdk を使う。

受け付けの流れ（inbox.Receiver）は M2 のままで、ここではその出入口だけを A2A にする。
- 封筒は、Message の Part 1つ（data に封筒、mediaType は application/json）で受け取る。
- 仕事の結果は Artifact で、入力を求める・断る・誤りを知らせる封筒はタスクの状態に添えて返す。
- プロファイルを扱えることは、AgentCard の拡張として宣言する。
- 必須の拡張を名乗らない要求と、再送は、A2A の部品がタスクを探す前に見分ける
  （ProfileRequestHandler）。

A2A の Part の data は、数をすべて小数つきの形で運ぶ（18 が 18.0 になって届く）。
そのため、受け取った封筒では、小数部が 0 の数を整数に戻してから扱う。
待ち受けは、このパソコンの中（127.0.0.1）だけで行う。認証はしていない。
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import uvicorn
from a2a.client import ClientCallContext, ClientConfig, create_client
from a2a.client.card_resolver import A2ACardResolver
from a2a.client.service_parameters import ServiceParametersFactory, with_a2a_extensions
from a2a.extensions.common import HTTP_EXTENSION_HEADER, find_extension_by_uri
from a2a.helpers.proto_helpers import new_data_part, new_task, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentExtension,
    AgentInterface,
    AgentSkill,
    Artifact,
    Message,
    Part,
    Role,
    SendMessageRequest,
    Task,
    TaskState,
    TaskStatus,
)
from a2a.utils.errors import ExtensionSupportRequiredError
from google.protobuf.json_format import MessageToDict
from starlette.applications import Starlette

from . import __version__
from .inbox import Outcome, Receiver, Reply, error_payload
from .messages import normalize_numbers
from .profile import (
    MEDIA_TYPE,
    MESSAGE_TYPES,
    PROFILE,
    PROFILE_URI,
    REJECTED,
    SUPPORTED_PROFILE_VERSIONS,
)

A2A_PROTOCOL_VERSION = "1.0"
_JST = timezone(timedelta(hours=9))


def envelope_part(envelope: Any) -> Part:
    """封筒を、A2A の Part 1つにする。"""
    return new_data_part(envelope, MEDIA_TYPE)


def read_envelope(parts: Any) -> Any:
    """A2A の Part の並びから封筒を取り出す。

    Part がちょうど1つで、data を持つときだけ封筒とみなす。それ以外は None を返し、
    受け付けの側で「検証の誤り」として扱う。
    """
    parts = list(parts)
    if len(parts) != 1 or not parts[0].HasField("data"):
        return None
    return normalize_numbers(MessageToDict(parts[0].data))


def build_agent_card(
    *, name: str, description: str, url: str, roles: list[str], accepts: list[str]
) -> AgentCard:
    """プロファイルを拡張として宣言した AgentCard を作る。"""
    extension = AgentExtension(
        uri=PROFILE_URI,
        description=(
            "Trade messages of the experimental trade-agent-profile. One message is one data "
            "Part (application/json) holding the envelope. Not an official specification of "
            "any standards body."
        ),
        required=True,
        params={
            "profile": PROFILE,
            "profile_versions": list(SUPPORTED_PROFILE_VERSIONS),
            "roles": roles,
            "accepts": accepts,
        },
    )
    skill = AgentSkill(
        id="trade-messages",
        name="Trade messages (trade-agent-profile)",
        description=description,
        tags=["trade", "shipment", "customs", "trade-agent-profile"],
        input_modes=[MEDIA_TYPE],
        output_modes=[MEDIA_TYPE],
    )
    return AgentCard(
        name=name,
        description=description,
        version=__version__,
        supported_interfaces=[
            AgentInterface(
                url=url, protocol_binding="JSONRPC", protocol_version=A2A_PROTOCOL_VERSION
            )
        ],
        capabilities=AgentCapabilities(
            streaming=False, push_notifications=False, extensions=[extension]
        ),
        default_input_modes=[MEDIA_TYPE],
        default_output_modes=[MEDIA_TYPE],
        skills=[skill],
    )


class ProfileExecutor(AgentExecutor):
    """受け付けの流れを、A2A のエージェントとして動かす。"""

    def __init__(self, receiver: Receiver) -> None:
        self.receiver = receiver

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        message = context.message
        task_id, context_id = context.task_id, context.context_id
        assert task_id and context_id
        continuing = context.current_task is not None
        if not continuing:
            history = [message] if message is not None else []
            await event_queue.enqueue_event(
                new_task(task_id, context_id, TaskState.TASK_STATE_SUBMITTED, history=history)
            )

        envelope = read_envelope(message.parts) if message is not None else None
        outcome = self.receiver.receive(
            envelope, task_id if continuing else None, assigned_task_id=task_id
        )
        if outcome.duplicate:
            # 再送がここまで届くのは、同じメッセージがほぼ同時に2つ届いたときなど。
            # 処理はせず、控えてある封筒を、いま振られたタスクに載せて返す
            self.receiver.adopt(task_id, outcome.state)

        updater = TaskUpdater(event_queue, task_id, context_id)
        for artifact in outcome.artifacts:
            await updater.add_artifact(
                [envelope_part(artifact)],
                artifact_id=artifact["message_id"],
                name=artifact["message_type"],
                extensions=[PROFILE_URI],
            )
        status_message = None
        if outcome.status_message is not None:
            status_message = _status_message(outcome.status_message, task_id, context_id)
        await updater.update_status(
            TaskState.Value(outcome.state), message=status_message, timestamp=outcome.at
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id and context.context_id
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


def _status_message(envelope: dict[str, Any], task_id: str, context_id: str) -> Message:
    """タスクの状態に添える Message。A2A の messageId には、封筒の message_id を使う。"""
    return Message(
        message_id=envelope["message_id"],
        role=Role.ROLE_AGENT,
        task_id=task_id,
        context_id=context_id,
        parts=[envelope_part(envelope)],
        extensions=[PROFILE_URI],
    )


def _answer_again(outcome: Outcome, stored: Task | None, context_id: str) -> Task:
    """控えてある結果から、最初に返したのと同じタスクを組み立て直す（再送への返事）。"""
    task = Task()
    if stored is not None:
        task.CopyFrom(stored)
    else:  # タスクの控えがもう残っていないとき
        task.id = outcome.task_id
        task.context_id = context_id
    del task.artifacts[:]
    for artifact in outcome.artifacts:
        task.artifacts.append(
            Artifact(
                artifact_id=artifact["message_id"],
                name=artifact["message_type"],
                parts=[envelope_part(artifact)],
                extensions=[PROFILE_URI],
            )
        )
    status = TaskStatus(state=TaskState.Value(outcome.state))
    if outcome.status_message is not None:
        status.message.CopyFrom(_status_message(outcome.status_message, task.id, task.context_id))
    status.timestamp.FromDatetime(datetime.fromisoformat(outcome.at))
    task.status.CopyFrom(status)
    return task


class ProfileRequestHandler(DefaultRequestHandler):
    """A2A の部品がタスクを探す前に、このプロファイルの2つの決まりを確かめる。

    1. 必須の拡張（A2A 3.3.4）：プロファイルを必須（required: true）と宣言しているとき、
       使うと名乗らない要求（A2A-Extensions ヘッダに識別 URI がない）は、
       ExtensionSupportRequiredError で断る。
    2. 再送（A2A 3.3.1 は messageId で重複を見つけてよいとしている）：同じ message_id・
       同じ中身のメッセージには、処理をやり直さず、最初と同じタスクと封筒を返す。
       続きとして送ったメッセージの再送にも、そのタスクが終わったあとでも、同じ返事を返す。
    """

    required_extension: str | None = None
    receiver: Receiver | None = None
    tasks: Any = None  # タスクの控え（A2A の部品の TaskStore）

    async def on_message_send(self, params: Any, context: Any) -> Any:
        required = self.required_extension
        if required and required not in context.requested_extensions:
            raise ExtensionSupportRequiredError(
                f"This agent requires the extension {required}. "
                f"Send its URI in the {HTTP_EXTENSION_HEADER} header."
            )
        if self.receiver is not None:
            outcome = self.receiver.processed(read_envelope(params.message.parts))
            if outcome is not None:
                stored = await self.tasks.get(outcome.task_id, context) if self.tasks else None
                context_id = params.message.context_id or str(uuid.uuid4())
                return _answer_again(outcome, stored, context_id)
        return await super().on_message_send(params, context)


def build_handler(receiver: Receiver, card: AgentCard, **options: Any) -> ProfileRequestHandler:
    """要求を受ける部品を組み立てる。拡張を必須とするかどうかは、AgentCard の宣言に合わせる。

    options は、A2A の部品（DefaultRequestHandler）にそのまま渡す。たとえば
    validate_input_modes=True とすると、AgentCard に書いていない種類（text/plain など）の
    Part を、A2A の ContentTypeNotSupportedError で断るようになる。
    """
    tasks = InMemoryTaskStore()
    handler = ProfileRequestHandler(
        agent_executor=ProfileExecutor(receiver), task_store=tasks, agent_card=card, **options
    )
    handler.receiver = receiver
    handler.tasks = tasks
    declared = find_extension_by_uri(card, PROFILE_URI)
    if declared is not None and declared.required:
        handler.required_extension = PROFILE_URI
    return handler


def build_app(
    receiver: Receiver, card: AgentCard, handler: DefaultRequestHandler | None = None
) -> Starlette:
    """A2A のエージェントとして待ち受けるアプリを組み立てる。

    AgentCard は A2A の決まった場所（/.well-known/agent-card.json）で、
    要求は JSON-RPC で受ける。
    """
    handler = handler or build_handler(receiver, card)
    routes = [*create_agent_card_routes(card), *create_jsonrpc_routes(handler, rpc_url="/")]
    return Starlette(routes=routes)


def decline_everything(envelope: dict[str, Any]) -> Reply:
    """何も引き受けない受け手（荷主側のエージェントの受付に使う）。"""
    return Reply(REJECTED, "error", error_payload("UNEXPECTED_MESSAGE"))


def free_port() -> int:
    """このパソコンの中で空いているポート番号を1つ選ぶ。"""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@contextmanager
def serve(app: Starlette, port: int) -> Iterator[str]:
    """アプリを、このパソコンの中だけ（127.0.0.1）で待ち受けさせる。外には開かない。"""
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError(f"ポート {port} で待ち受けを始められませんでした")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


async def fetch_card(url: str, http: Any = None) -> AgentCard:
    """相手の AgentCard を取りに行く（/.well-known/agent-card.json）。"""
    if http is not None:
        return await A2ACardResolver(http, url).get_agent_card()
    import httpx

    async with httpx.AsyncClient() as client:
        return await A2ACardResolver(client, url).get_agent_card()


def _to_local_time(task: Task) -> str:
    moment = task.status.timestamp.ToDatetime(tzinfo=UTC)
    return moment.astimezone(_JST).isoformat(timespec="seconds")


def outcome_from_task(task: Task, duplicate: bool = False) -> Outcome:
    """返ってきた A2A のタスクを、受け付けの結果の形に読み替える。"""
    artifacts = [read_envelope(artifact.parts) for artifact in task.artifacts]
    status_message = None
    if task.status.HasField("message"):
        status_message = read_envelope(task.status.message.parts)
    replies = [*artifacts, status_message]
    sent_at = next((r["sent_at"] for r in replies if isinstance(r, dict) and "sent_at" in r), None)
    return Outcome(
        task_id=task.id,
        state=TaskState.Name(task.status.state),
        at=sent_at or _to_local_time(task),
        artifacts=artifacts,
        status_message=status_message,
        duplicate=duplicate,
    )


class A2ALink:
    """封筒を A2A で相手に送る側。"""

    def __init__(self, card: AgentCard, http: Any = None) -> None:
        self.card = card
        self.http = http
        self.contexts: dict[str, str] = {}  # 会話（correlation_id）→ 相手が振った contextId
        self.tasks: dict[str, Task] = {}  # 送った message_id → 返ってきたタスク
        self.last_task: Task | None = None

    async def send(
        self,
        envelope: Any = None,
        task_id: str | None = None,
        *,
        text: str | None = None,
        declare_extension: bool = True,
    ) -> Outcome:
        """封筒を1つ送る。text を渡すと、封筒の代わりに文字だけのメッセージを送る。

        declare_extension を False にすると、プロファイルを使うと名乗らずに送る
        （A2A-Extensions ヘッダを付けない。適合テストで、断られることを確かめるために使う）。
        """
        usable = isinstance(envelope, dict)
        message_id = envelope.get("message_id") if usable else None
        if not isinstance(message_id, str) or not message_id:
            message_id = str(uuid.uuid4())
        correlation = envelope.get("correlation_id") if usable else None
        part = new_text_part(text, "text/plain") if text is not None else envelope_part(envelope)
        message = Message(message_id=message_id, role=Role.ROLE_USER, parts=[part])
        if declare_extension:
            message.extensions.append(PROFILE_URI)
        if task_id:
            message.task_id = task_id
        elif isinstance(correlation, str) and correlation in self.contexts:
            message.context_id = self.contexts[correlation]

        duplicate = message_id in self.tasks
        task = await self._send(message, declare_extension)
        self.last_task = task
        self.tasks[message_id] = task
        if isinstance(correlation, str) and task.context_id:
            self.contexts.setdefault(correlation, task.context_id)
        return outcome_from_task(task, duplicate)

    async def _send(self, message: Message, declare_extension: bool = True) -> Task:
        config = ClientConfig(streaming=False, httpx_client=self.http)
        client = await create_client(self.card, client_config=config)
        updates = [with_a2a_extensions([PROFILE_URI])] if declare_extension else []
        parameters = ServiceParametersFactory.create(updates)
        call = ClientCallContext(service_parameters=parameters)
        task: Task | None = None
        try:
            request = SendMessageRequest(message=message)
            async for response in client.send_message(request, context=call):
                if response.HasField("task"):
                    task = response.task
        finally:
            if self.http is None:
                await client.close()
        if task is None:
            raise RuntimeError("相手からタスクが返りませんでした")
        return task

    def receive(self, envelope: Any, task_id: str | None = None) -> Outcome:
        """通信をしない側（台本デモ）から、同じ呼び方で使うための入口。"""
        return asyncio.run(self.send(envelope, task_id))


def card_summary(card: AgentCard) -> dict[str, Any]:
    """AgentCard から、プロファイルに関わる部分を抜き出す。"""
    declared = [
        extension for extension in card.capabilities.extensions if extension.uri == PROFILE_URI
    ]
    params = normalize_numbers(MessageToDict(declared[0].params)) if declared else {}
    return {
        "name": card.name,
        "interfaces": [
            {"url": i.url, "binding": i.protocol_binding, "version": i.protocol_version}
            for i in card.supported_interfaces
        ],
        "declares_profile": bool(declared),
        "required": bool(declared and declared[0].required),
        "profile": params.get("profile"),
        "profile_versions": params.get("profile_versions", []),
        "roles": params.get("roles", []),
        "accepts": params.get("accepts", []),
        "known_types": [kind for kind in params.get("accepts", []) if kind in MESSAGE_TYPES],
    }
