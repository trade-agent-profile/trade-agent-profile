"""A2A の通信に載せた受け付けと、適合テスト。実際にこのパソコンの中で通信して確かめる。"""

from __future__ import annotations

import asyncio
import copy
import json
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import httpx
import make_samples
import pytest
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from a2a.utils.errors import ContentTypeNotSupportedError, ExtensionSupportRequiredError
from conftest import ROOT, SAMPLES, load_json
from google.protobuf.json_format import MessageToDict
from starlette.applications import Starlette

from trade_agent_profile import i18n, validate_message
from trade_agent_profile.a2a_agent import (
    A2A_PROTOCOL_VERSION,
    A2ALink,
    ProfileExecutor,
    build_agent_card,
    build_app,
    build_handler,
    card_summary,
    envelope_part,
    fetch_card,
    free_port,
    read_envelope,
    serve,
)
from trade_agent_profile.conformance import (
    CaseResult,
    _Filler,
    applies,
    check_card,
    load_cases,
    run_conformance,
)
from trade_agent_profile.demo import MAIN_SCENES, load_demo_shipment, run_demo
from trade_agent_profile.inbox import InboxStore, Outcome, Receiver
from trade_agent_profile.messages import UUID_RE, digest, new_message, normalize_numbers
from trade_agent_profile.profile import COMPLETED, INPUT_REQUIRED, PROFILE, PROFILE_URI
from trade_agent_profile.reference import (
    BROKER_ACCEPTS,
    broker_app,
    broker_card,
    broker_receiver,
    new_uuid,
    now_text,
    quiet_logs,
    shipper_app,
)
from trade_agent_profile.report import render

CASES = ROOT / "conformance" / "cases"
ALL_IDS = [f"C{number:02d}" for number in range(1, 18)]
SHIPPER = {"role": "shipper", "name": "Demo Resource Recovery Co., Ltd.", "id": "test-client"}


@dataclass
class Running:
    """待ち受けている1つのエージェント。"""

    url: str
    card: AgentCard
    receiver: Receiver | None = None


@contextmanager
def running(app: Starlette, card: AgentCard, port: int) -> Iterator[Running]:
    quiet_logs()
    with serve(app, port) as url:
        yield Running(url, card)


@pytest.fixture(scope="module")
def broker() -> Iterator[Running]:
    """見本の相手側エージェント（フォワーダー兼通関業者）。"""
    port = free_port()
    receiver = broker_receiver()
    app, card = broker_app(port, receiver)
    with running(app, card, port) as agent:
        agent.receiver = receiver
        yield agent


def conformance(agent: Running) -> dict[str, CaseResult]:
    results = asyncio.run(run_conformance(agent.card, load_cases(CASES)))
    return {result.case_id: result for result in results}


def failed(results: dict[str, CaseResult]) -> dict[str, list[str]]:
    """不合格のテストと、その理由（文言の鍵）。"""
    return {
        case_id: [key for key, _ in result.problems]
        for case_id, result in results.items()
        if result.problems
    }


def quote_request() -> dict[str, Any]:
    """新しい見積依頼（識別子は毎回新しい）。"""
    shipment = load_demo_shipment()
    shipment["status"] = "draft"
    shipment["documents"] = []
    shipment["events"] = shipment["events"][:1]
    payload = {"shipment": shipment, "reply_by": None, "note": None}
    return new_message(
        "quote_request", payload, sender=SHIPPER, correlation_id=new_uuid(), sent_at=now_text()
    )


# ---- AgentCard ----


def test_agent_card_is_served_and_declares_the_profile_as_an_extension(broker: Running) -> None:
    """A2A の決まった場所から AgentCard が取れ、プロファイルが拡張として宣言されている。"""
    raw = httpx.get(f"{broker.url}/.well-known/agent-card.json").json()
    interface = raw["supportedInterfaces"][0]
    assert interface["protocolBinding"] == "JSONRPC"
    assert interface["protocolVersion"] == A2A_PROTOCOL_VERSION
    assert interface["url"].startswith("http://127.0.0.1:")  # このパソコンの中だけ
    extension = raw["capabilities"]["extensions"][0]
    assert extension["uri"] == PROFILE_URI
    assert extension["required"] is True
    assert extension["params"]["profile"] == PROFILE
    assert extension["params"]["accepts"] == BROKER_ACCEPTS
    assert "streaming" not in raw["capabilities"] or raw["capabilities"]["streaming"] is False

    summary = card_summary(asyncio.run(fetch_card(broker.url)))
    assert summary["declares_profile"] and summary["required"]
    assert summary["profile_versions"] == ["0.1.0"]
    assert summary["roles"] == ["forwarder", "customs_broker"]
    assert check_card(broker.card) == []


def test_check_card_names_what_is_missing() -> None:
    card = broker_card("http://127.0.0.1:1/")
    del card.capabilities.extensions[:]
    assert [key for key, _ in check_card(card)] == ["card_no_extension"]

    card = broker_card("http://127.0.0.1:1/")
    card.capabilities.extensions[0].params["profile"] = "other-profile"
    card.capabilities.extensions[0].params["profile_versions"] = ["9.9.9"]
    card.supported_interfaces[0].protocol_version = "0.3"
    assert [key for key, _ in check_card(card)] == [
        "card_profile",
        "card_version",
        "card_interface",
    ]


# ---- 適合テスト ----


def test_reference_agent_passes_every_conformance_case(broker: Running) -> None:
    """M3 の完成条件：適合テストが全件合格する。"""
    results = conformance(broker)
    assert list(results) == ALL_IDS
    assert failed(results) == {}
    assert all(result.passed for result in results.values())


def test_shipper_agent_passes_the_cases_that_apply_to_it() -> None:
    """何も引き受けないエージェントでは、依頼を使うテストが対象外になり、残りは合格する。"""
    port = free_port()
    app, card = shipper_app(port)
    with running(app, card, port) as agent:
        results = conformance(agent)
    assert failed(results) == {}
    passed = [case_id for case_id, result in results.items() if result.passed]
    assert passed == ["C01", "C09", "C10", "C13", "C14", "C16"]
    assert all(result.skipped for case_id, result in results.items() if case_id not in passed)


def test_conformance_fails_when_the_required_extension_is_not_enforced() -> None:
    """必須と宣言しながら、名乗らない要求を通してしまう実装は、C16 で不合格になる。"""
    port = free_port()
    card = broker_card(f"http://127.0.0.1:{port}/")
    receiver = broker_receiver()
    handler = build_handler(receiver, card)
    assert handler.required_extension == PROFILE_URI  # ふつうは、宣言に合わせて確かめる
    handler.required_extension = None
    with running(build_app(receiver, card, handler), card, port) as agent:
        assert failed(conformance(agent)) == {"C16": ["p_a2a_error_missing"]}


def test_conformance_fails_when_resends_are_only_caught_after_the_task_lookup() -> None:
    """再送をタスクを探したあとで見分ける実装。

    新しいタスクとして届く再送には、同じ封筒を新しいタスクに載せて返せる（C07 は合格）。
    しかし、終わったタスクの続きとして届く再送は A2A のエラーになる（C17 が不合格）。
    必須の拡張も確かめていないので、C16 も不合格になる。
    """
    port = free_port()
    card = broker_card(f"http://127.0.0.1:{port}/")
    receiver = broker_receiver()
    handler = DefaultRequestHandler(  # A2A の部品を、そのまま使った受付
        agent_executor=ProfileExecutor(receiver), task_store=InMemoryTaskStore(), agent_card=card
    )
    with running(build_app(receiver, card, handler), card, port) as agent:
        results = conformance(agent)
    assert failed(results) == {"C16": ["p_a2a_error_missing"], "C17": ["p_error"]}
    assert results["C07"].passed


def test_agent_that_refuses_text_with_an_a2a_error_also_passes() -> None:
    """封筒でないメッセージを、A2A の ContentTypeNotSupportedError で断る実装も合格にする。

    AgentCard に書いた種類（application/json）以外を A2A のエラーで断るのは、A2A の
    決まりに沿った答え方（3.1.1）。C13 は、どちらの答え方でも合格になる。
    """
    port = free_port()
    card = broker_card(f"http://127.0.0.1:{port}/")
    receiver = broker_receiver()
    handler = build_handler(receiver, card, validate_input_modes=True)
    with running(build_app(receiver, card, handler), card, port) as agent:
        with pytest.raises(ContentTypeNotSupportedError):
            asyncio.run(A2ALink(agent.card).send(text="Hello"))
        assert failed(conformance(agent)) == {}


class ForgetfulStore(InboxStore):
    """受け付けたメッセージを覚えない控え（二重処理を防げない実装）。"""

    def get(self, message_id: str) -> tuple[str, Outcome] | None:
        return None

    def put(self, message_id: str, fingerprint: str, outcome: Outcome) -> None:
        return None


def test_conformance_fails_when_messages_are_processed_twice() -> None:
    port = free_port()
    receiver = broker_receiver(store=ForgetfulStore())
    app, card = broker_app(port, receiver)
    with running(app, card, port) as agent:
        problems = failed(conformance(agent))
    assert problems["C07"] == ["p_same_reply"]  # 再送に、作り直した別の見積が返る
    assert "p_state" in problems["C08"]  # 中身の違う使い回しを、断らずに処理してしまう
    assert set(problems) == {"C07", "C08", "C17"}


class MisplacingReceiver(Receiver):
    """仕事の結果を、Artifact ではなくタスクの状態に添えて返してしまう実装。"""

    def receive(self, envelope: Any, task_id: str | None = None, **more: Any) -> Outcome:
        outcome = super().receive(envelope, task_id, **more)
        if outcome.artifacts:
            outcome.status_message, outcome.artifacts = outcome.artifacts[0], []
        return outcome


def test_conformance_fails_when_results_are_not_returned_as_artifacts() -> None:
    port = free_port()
    honest = broker_receiver()
    receiver = MisplacingReceiver(
        honest.handler, sender=honest.sender, store=InboxStore(), clock=now_text, new_id=new_uuid
    )
    app, card = broker_app(port, receiver)
    with running(app, card, port) as agent:
        problems = failed(conformance(agent))
    assert problems["C02"] == ["p_reply_place"]
    assert all("p_reply_place" in keys for keys in problems.values())
    assert "C09" not in problems  # 断る返事は、もともと状態に添えるもの


def test_applies_follows_what_the_agent_card_declares() -> None:
    case = {"needs": ["quote_request"], "refuses": ["quote"]}
    assert applies(case, ["quote_request"])
    assert not applies(case, [])  # 見積依頼を引き受けない相手には行わない
    assert not applies(case, ["quote_request", "quote"])  # quote を引き受ける相手には行わない
    assert applies({"extension_required": True}, [], required=True)
    assert not applies({"extension_required": True}, [], required=False)


def test_placeholders_in_cases_are_filled_at_run_time() -> None:
    filler = _Filler()
    filler.replies[1] = {"message_id": "abc", "payload": {"quote_number": "Q-1"}}
    filled = filler.fill(
        {
            "a": "$id:m1",
            "b": ["$id:m1", "$id:m2"],
            "c": "$now",
            "d": "$reply:1:payload.quote_number",
            "e": "$reply:2:message_id",
            "f": "plain",
            "g": 5,
        }
    )
    assert filled["a"] == filled["b"][0] != filled["b"][1]
    assert filled["c"].endswith("+09:00")
    assert (filled["d"], filled["e"], filled["f"], filled["g"]) == ("Q-1", None, "plain", 5)


def test_conformance_case_files_are_exactly_the_generated_ones() -> None:
    """conformance/cases/ は道具（make_samples.py）が作ったものだけで、手で足したものがない。"""
    generated = {name for name in make_samples.build_all() if name.startswith("conformance/")}
    on_disk = {path.relative_to(ROOT).as_posix() for path in CASES.glob("*")}
    assert on_disk == generated
    assert [case["id"] for case in load_cases(CASES)] == ALL_IDS
    for case in load_cases(CASES):
        assert set(case["title"]) == set(i18n.LANGS)
        text = json.dumps(case)
        assert "Demo" in text or case["id"] in ("C01", "C13")  # 当事者は架空の名前だけ


def test_conformance_command_reports_in_json_and_by_exit_code(broker: Running) -> None:
    """第三者が使う命令：合格なら終了コード 0、相手につながらなければ 2。"""
    script = str(ROOT / "scripts" / "conformance.py")
    done = subprocess.run(
        [sys.executable, script, "--target", broker.url, "--json"],
        capture_output=True,
        cwd=ROOT,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    report = json.loads(done.stdout.decode("utf-8"))
    assert report["summary"] == {"total": 17, "passed": 17, "failed": 0, "skipped": 0}
    assert report["agent"]["declares_profile"] is True

    nowhere = f"http://127.0.0.1:{free_port()}"
    done = subprocess.run(
        [sys.executable, script, "--target", nowhere, "--lang", "ja"],
        capture_output=True,
        cwd=ROOT,
        timeout=120,
        check=False,
    )
    assert done.returncode == 2
    assert i18n.catalog("ja")["conformance"]["no_card"].split("（")[0] in done.stderr.decode(
        "utf-8"
    )


# ---- 受け付けを A2A に載せたときのふるまい ----


def test_result_comes_back_as_an_artifact_that_names_the_extension(broker: Running) -> None:
    link = A2ALink(broker.card)
    request = quote_request()
    outcome = asyncio.run(link.send(request))
    assert outcome.state == COMPLETED
    quote = outcome.artifacts[0]
    assert validate_message(quote).valid
    assert quote["in_reply_to"] == request["message_id"]

    task = MessageToDict(link.last_task)
    artifact = task["artifacts"][0]
    assert artifact["artifactId"] == quote["message_id"]
    assert artifact["name"] == "quote"
    assert artifact["extensions"] == [PROFILE_URI]
    assert artifact["parts"][0]["mediaType"] == "application/json"
    assert "message" not in task["status"]  # 結果は、状態には添えない


def test_notice_comes_back_on_the_task_status_and_the_task_can_be_continued(
    broker: Running,
) -> None:
    link = A2ALink(broker.card)
    request = quote_request()
    del request["payload"]["reply_by"]
    outcome = asyncio.run(link.send(request))
    assert outcome.state == INPUT_REQUIRED
    assert outcome.artifacts == []
    notice = outcome.status_message
    assert notice["payload"]["code"] == "VALIDATION_FAILED"

    status = MessageToDict(link.last_task)["status"]["message"]
    assert status["messageId"] == notice["message_id"]  # A2A の messageId は封筒と同じ
    assert status["role"] == "ROLE_AGENT"
    assert status["extensions"] == [PROFILE_URI]

    fixed = quote_request()
    fixed["correlation_id"] = request["correlation_id"]
    again = asyncio.run(link.send(fixed, outcome.task_id))
    assert again.state == COMPLETED
    assert again.task_id == outcome.task_id  # 同じタスクの続き
    assert again.artifacts[0]["message_type"] == "quote"


def test_resend_gets_the_very_same_task_and_is_processed_once(broker: Running) -> None:
    """M2 から続く完成条件：同じ message_id の再送は、通信を通しても二重処理されない。"""
    agent = broker.receiver.handler
    link = A2ALink(broker.card)
    request = quote_request()
    before = agent.calls
    first = asyncio.run(link.send(request))
    first_task = MessageToDict(link.last_task)
    second = asyncio.run(link.send(copy.deepcopy(request)))
    second_task = MessageToDict(link.last_task)

    assert agent.calls == before + 1  # 実際に処理したのは1回だけ
    assert (first.duplicate, second.duplicate) == (False, True)
    assert second.task_id == first.task_id
    assert second.artifacts == first.artifacts
    for key in ("id", "contextId", "status", "artifacts"):
        assert second_task[key] == first_task[key], key


def test_two_copies_arriving_at_the_same_time_are_processed_once(broker: Running) -> None:
    """同じメッセージがほぼ同時に2つ届いても、処理は1回だけで、同じ封筒が返る。"""
    agent = broker.receiver.handler
    request = quote_request()
    before = agent.calls

    async def both() -> list[Outcome]:
        return await asyncio.gather(
            A2ALink(broker.card).send(request),
            A2ALink(broker.card).send(copy.deepcopy(request)),
        )

    first, second = asyncio.run(both())
    assert agent.calls == before + 1
    assert first.state == second.state == COMPLETED
    assert first.artifacts == second.artifacts
    # そのあとの再送には、処理した方のタスクが返る
    again = asyncio.run(A2ALink(broker.card).send(copy.deepcopy(request)))
    assert again.artifacts == first.artifacts
    assert again.task_id in (first.task_id, second.task_id)
    assert agent.calls == before + 1


def test_same_message_id_with_other_content_is_refused(broker: Running) -> None:
    agent = broker.receiver.handler
    link = A2ALink(broker.card)
    request = quote_request()
    asyncio.run(link.send(request))
    before = agent.calls
    changed = copy.deepcopy(request)
    changed["payload"]["note"] = "Changed after the first sending."
    outcome = asyncio.run(link.send(changed))
    assert outcome.state == "TASK_STATE_REJECTED"
    assert outcome.status_message["payload"]["code"] == "MESSAGE_ID_REUSED"
    assert agent.calls == before


def test_request_that_does_not_declare_the_extension_is_refused(broker: Running) -> None:
    """A2A 3.3.4：必須の拡張を使うと名乗らない要求には、決まったエラーを返す。"""
    agent = broker.receiver.handler
    before = agent.calls
    with pytest.raises(ExtensionSupportRequiredError):
        asyncio.run(A2ALink(broker.card).send(quote_request(), declare_extension=False))
    assert agent.calls == before


# ---- 数の扱い ----


def test_whole_numbers_are_restored_after_the_trip() -> None:
    value = {"a": 18.0, "b": 0.5, "c": [1.0, {"d": 2.0}], "e": "1.0", "f": True, "g": None}
    restored = normalize_numbers(value)
    assert restored == {"a": 18, "b": 0.5, "c": [1, {"d": 2}], "e": "1.0", "f": True, "g": None}
    assert type(restored["a"]) is int and type(restored["c"][0]) is int
    assert type(restored["f"]) is bool  # 真偽は数に変えない
    # 中身の指紋は、数の書き方（18 と 18.0）や項目の並び順では変わらない
    assert digest({"a": 18.0, "b": [1.0]}) == digest({"b": [1], "a": 18})
    assert digest({"a": 18.5}) != digest({"a": 18})


@pytest.mark.parametrize(
    "path", sorted((SAMPLES / "messages").glob("*.json")), ids=lambda p: p.stem
)
def test_every_sample_message_survives_the_trip_unchanged(path: Any) -> None:
    """A2A の Part に載せて取り出しても、封筒が同じで、中身の指紋も変わらないこと。"""
    envelope = load_json(path)
    carried = read_envelope([envelope_part(envelope)])
    assert carried == envelope
    assert digest(carried) == digest(envelope)
    assert validate_message(carried).valid == validate_message(envelope).valid


def test_only_a_single_data_part_is_read_as_an_envelope() -> None:
    from a2a.helpers.proto_helpers import new_text_part

    envelope = load_json(SAMPLES / "messages" / "01_quote_request.json")
    assert read_envelope([new_text_part("Hello")]) is None
    assert read_envelope([envelope_part(envelope), envelope_part(envelope)]) is None
    assert read_envelope([]) is None


# ---- 台本デモを A2A で ----


@pytest.fixture(scope="module")
def a2a_demo() -> Any:
    """台本デモを、実際の A2A の通信で1回実行する。"""
    quiet_logs()
    cards: list[dict[str, Any]] = []
    stack: list[Any] = []

    def connect(receiver: Receiver) -> A2ALink:
        port = free_port()
        app, card = broker_app(port, receiver)
        context = serve(app, port)
        context.__enter__()
        stack.append(context)
        cards.append(card_summary(card))
        return A2ALink(card)

    try:
        run = run_demo(connect=connect)
    finally:
        for context in stack:
            context.__exit__(None, None, None)
    return run, cards


def renumbered(entries: list[Any]) -> list[dict[str, Any]]:
    """記録の中の識別子（UUID）を、初めて出てきた順の番号に置き換える。

    通信ありとなしでは、識別子を振る回数が違うので、識別子そのものは一致しない。
    置き換えたあとが同じなら、やり取りの中身と、返事がどれを指すかの関係が同じだと言える。
    タスクの識別子は、通信の部品が振るので、ここでは比べない。
    """
    numbers: dict[str, str] = {}

    def swap(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: swap(value[key]) for key in sorted(value)}
        if isinstance(value, list):
            return [swap(item) for item in value]
        if isinstance(value, str) and UUID_RE.match(value):
            return numbers.setdefault(value, f"id-{len(numbers) + 1}")
        return value

    names = ("scene", "at", "sender", "kind", "envelope", "state", "duplicate")
    return [swap({name: getattr(entry, name) for name in names}) for entry in entries]


def test_demo_over_a2a_exchanges_the_same_messages_as_the_in_process_demo(a2a_demo: Any) -> None:
    """M3：2つのエージェントが、A2A の通信で台本を最後までやり取りする。"""
    run, _ = a2a_demo
    local = run_demo()
    wired, plain = renumbered(run.entries), renumbered(local.entries)
    assert len(wired) == len(plain)
    for number, (sent, expected) in enumerate(zip(wired, plain, strict=True), 1):
        assert sent == expected, number
    assert run.broker.calls == local.broker.calls == 7


def test_demo_over_a2a_uses_task_ids_given_by_the_receiving_agent(a2a_demo: Any) -> None:
    run, _ = a2a_demo
    tasks = {
        scene: next(e.task_id for e in run.entries if e.scene == scene and e.sender == "broker")
        for scene in (*MAIN_SCENES, "resend")
    }
    assert tasks["documents"] == tasks["resubmission"]  # 直した再提出は、同じタスクの続き
    assert tasks["resend"] == tasks["booking"]  # 再送には、最初と同じタスクが返る
    assert len(set(tasks.values())) == 4
    local = {entry.task_id for entry in run_demo().entries}
    assert not (set(tasks.values()) & local)  # 台本の識別子ではなく、通信の部品が振ったもの


def test_report_of_the_a2a_demo_says_it_was_really_sent_and_shows_the_cards(a2a_demo: Any) -> None:
    run, cards = a2a_demo
    report = i18n.catalog("ja")["report"]
    html = render(run.entries, wire="a2a", cards=cards)
    assert report["transport_note_a2a"] in html and report["transport_note"] not in html
    assert report["footer_a2a"] in html
    assert report["cards_title"] in html
    assert "quote_request, booking_request" in html  # 引き受ける種類
    assert i18n.catalog("ja")["ui"]["notice"] in html

    plain = render(run.entries)
    assert report["transport_note"] in plain and report["cards_title"] not in plain


def test_agent_card_can_be_built_for_any_role() -> None:
    card = build_agent_card(
        name="Demo Bank", description="demo", url="http://127.0.0.1:1/", roles=["bank"], accepts=[]
    )
    summary = card_summary(card)
    assert summary["roles"] == ["bank"] and summary["accepts"] == []
    assert summary["interfaces"][0]["binding"] == "JSONRPC"
