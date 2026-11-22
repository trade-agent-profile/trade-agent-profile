"""台本デモと、その HTML の記録。"""

from __future__ import annotations

import pytest
from conftest import ROOT

from trade_agent_profile import i18n, validate_message
from trade_agent_profile.demo import EXTRA_SCENES, MAIN_SCENES, DemoRun, run_demo
from trade_agent_profile.profile import COMPLETED, INPUT_REQUIRED, MESSAGE_TYPES, REJECTED
from trade_agent_profile.report import render

REPORT = ROOT / "reports" / "demo.html"


@pytest.fixture(scope="module")
def run() -> DemoRun:
    return run_demo()


def steps(run: DemoRun, scenes: tuple[str, ...]) -> list[tuple[str, str | None, str | None]]:
    return [
        (entry.sender, entry.envelope["message_type"] if entry.envelope else None, entry.state)
        for entry in run.entries
        if entry.scene in scenes
    ]


def test_main_flow_runs_from_quote_request_to_approval(run: DemoRun) -> None:
    """M2 の完成条件：見積依頼から承認までが、最後まで走る。"""
    assert steps(run, MAIN_SCENES) == [
        ("shipper", "quote_request", None),
        ("broker", "quote", COMPLETED),
        ("shipper", "booking_request", None),
        ("broker", "booking_confirmation", COMPLETED),
        ("shipper", "document_submission", None),
        ("broker", "discrepancy_notice", INPUT_REQUIRED),
        ("shipper", "document_submission", None),
        ("broker", "declaration_draft", COMPLETED),
        ("shipper", "approval", None),
        ("broker", None, COMPLETED),
    ]
    thread = next(iter(run.broker.threads.values()))
    assert thread["approved"] is True


def test_extra_scenes_show_resend_version_mismatch_and_declining(run: DemoRun) -> None:
    assert steps(run, EXTRA_SCENES) == [
        ("shipper", "booking_request", None),
        ("broker", "booking_confirmation", COMPLETED),
        ("shipper", "quote_request", None),
        ("broker", "error", REJECTED),
        ("shipper", "quote_request", None),
        ("broker", "quote", COMPLETED),
        ("shipper", "rejection", None),
        ("broker", None, COMPLETED),
    ]
    resend = [entry for entry in run.entries if entry.scene == "resend"]
    assert all(entry.duplicate for entry in resend)
    original = next(e for e in run.entries if e.scene == "booking" and e.sender == "broker")
    assert resend[1].envelope == original.envelope  # 最初の結果がそのまま返る
    # 実際に処理したのは 見積依頼・ブッキング依頼・書類の提出2回・承認・見積依頼・辞退 の7回
    assert run.broker.calls == 7


def test_all_ten_message_types_appear_and_are_valid(run: DemoRun) -> None:
    envelopes = [entry.envelope for entry in run.entries if entry.envelope is not None]
    assert {envelope["message_type"] for envelope in envelopes} == set(MESSAGE_TYPES)
    for envelope in envelopes:
        if envelope["profile_version"] == "0.2.0":
            continue  # 版が合わない場面のために、わざと送っているもの
        result = validate_message(envelope)
        assert result.valid, [(issue.code, issue.path) for issue in result.errors]


def test_replies_point_to_the_message_they_answer(run: DemoRun) -> None:
    sent = None
    for entry in run.entries:
        if entry.sender == "shipper":
            sent = entry.envelope
        elif entry.envelope is not None:
            assert entry.envelope["in_reply_to"] == sent["message_id"]
            assert entry.envelope["correlation_id"] == sent["correlation_id"]


def test_resubmission_continues_the_same_task(run: DemoRun) -> None:
    tasks = {
        scene: next(e.task_id for e in run.entries if e.scene == scene and e.sender == "broker")
        for scene in MAIN_SCENES
    }
    assert tasks["documents"] == tasks["resubmission"]
    assert len(set(tasks.values())) == 4  # 見積・ブッキング・書類（再提出も同じ）・承認


def test_declaration_draft_is_marked_as_mock_and_lists_unverified_items(run: DemoRun) -> None:
    draft = next(
        entry.envelope["payload"]
        for entry in run.entries
        if entry.envelope and entry.envelope["message_type"] == "declaration_draft"
    )
    assert draft["mock"] is True
    assert draft["unverified"] == ["lines[0].hs_code_jp", "lines[1].hs_code_jp"]
    assert draft["invoice_amount"] == "24270.00"
    assert "not a customs declaration" in draft["note"]


def test_demo_is_the_same_every_time(run: DemoRun) -> None:
    again = run_demo()
    assert [entry.__dict__ for entry in again.entries] == [entry.__dict__ for entry in run.entries]


def test_report_shows_the_required_notices_and_where_values_come_from(run: DemoRun) -> None:
    html = render(run.entries)
    ui, report = i18n.catalog("ja")["ui"], i18n.catalog("ja")["report"]
    assert ui["notice"] in html and ui["judge"] in html
    assert report["basis"]["rule"] in html and report["basis"]["unverified"] in html
    assert report["facts"]["mock_text"] in html
    for kind in MESSAGE_TYPES:
        assert f"<code>{kind}</code>" in html
    assert "TASK_STATE_INPUT_REQUIRED" in html and "TASK_STATE_REJECTED" in html
    assert "{{" not in html and "{%" not in html
    assert "http://" not in html.replace("https://", "")  # 外部のファイルは読み込まない
    assert "<script" not in html


def test_report_escapes_text_and_can_be_written_in_english(run: DemoRun) -> None:
    html = render(run.entries, "en")
    assert "Quote request" in html
    assert "Demo Forwarding &amp; Customs K.K." in html  # & がそのまま出ていない


def test_report_file_is_up_to_date(run: DemoRun) -> None:
    """reports/demo.html が、いまの台本デモの出力と同じであること。"""
    with REPORT.open(encoding="utf-8", newline="") as handle:
        assert handle.read() == render(run.entries)
