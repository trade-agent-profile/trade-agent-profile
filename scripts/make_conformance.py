"""適合テストの入力と期待出力（conformance/cases/）を作る。データはすべて架空。

make_samples.py から呼ばれる。台本デモと同じ架空の船積みを使う。
1つのファイルが1件のテストで、手順ごとに「送るもの」と「期待する答え」を持つ。
"""

from __future__ import annotations

import copy
from typing import Any

from trade_agent_profile.profile import (
    COMPLETED,
    INPUT_REQUIRED,
    PROFILE,
    PROFILE_VERSION,
    REJECTED,
)

Json = dict[str, Any]
SENDER = {"role": "shipper", "name": "Demo Resource Recovery Co., Ltd.", "id": "conformance-client"}
WRONG_GROSS_WEIGHT = "21480.000"  # 正本は 21840.000


def envelope(
    kind: str,
    payload: Json,
    *,
    message: str = "m1",
    thread: str = "thread",
    in_reply_to: str | None = None,
    role: str = "shipper",
    **override: Any,
) -> Json:
    """送る封筒のひな形。識別子と日時は、実行のときに置き換える書き方にしておく。"""
    result: Json = {
        "profile": PROFILE,
        "profile_version": PROFILE_VERSION,
        "message_type": kind,
        "message_id": f"$id:{message}",
        "correlation_id": f"$id:{thread}",
    }
    if in_reply_to is not None:
        result["in_reply_to"] = in_reply_to
    result["sent_at"] = "$now"
    result["sender"] = dict(SENDER, role=role)
    result["payload"] = payload
    result.update(override)
    return result


def reply(place: str, kind: str, **more: Any) -> Json:
    return {"in": place, "message_type": kind, **more}


def error(code: str, *issues: tuple[str, str]) -> Json:
    found = [{"code": issue_code, "path": path} for issue_code, path in issues]
    return reply("status", "error", code=code, issues=found)


def step(send: Json, state: str, answer: Json | None, **more: Any) -> Json:
    return {"send": send, **more, "expect": {"state": state, "reply": answer}}


def case(
    case_id: str,
    ja: str,
    en: str,
    steps: list[Json],
    *,
    needs: tuple[str, ...] = (),
    refuses: tuple[str, ...] = (),
    extension_required: bool = False,
) -> Json:
    """1件のテスト。

    needs は相手が引き受けている必要のある種類、refuses は引き受けていないことが条件の種類。
    extension_required が True のテストは、相手が拡張を必須と宣言しているときだけ行う。
    """
    return {
        "id": case_id,
        "title": {"ja": ja, "en": en},
        "needs": list(needs),
        "refuses": list(refuses),
        "extension_required": extension_required,
        "steps": steps,
    }


def conformance_cases(demo: Json) -> dict[str, Json]:
    """テストの一覧（ファイル名 → 中身）。demo は、書類の値が正本とそろった船積み。"""
    shipment_id = demo["shipment_id"]
    planned = copy.deepcopy(demo)  # 見積とブッキングの時点：書類はまだない
    planned["status"] = "draft"
    planned["documents"] = []
    planned["events"] = planned["events"][:1]

    wrong = copy.deepcopy(demo)  # パッキングリストの総重量が正本と違う
    wrong["documents"][1]["fields"]["totals.gross_weight_kg"]["value"] = WRONG_GROSS_WEIGHT
    discrepancy = {
        "doc_type": "packing_list",
        "doc_number": wrong["documents"][1]["doc_number"],
        "path": "totals.gross_weight_kg",
        "document_value": WRONG_GROSS_WEIGHT,
        "authoritative_value": demo["totals"]["gross_weight_kg"],
    }

    bad_container = copy.deepcopy(planned)  # コンテナ番号の検査数字が違う
    number = bad_container["transport"]["containers"][0]["number"]
    bad_number = number[:10] + str((int(number[10]) + 1) % 10)
    bad_container["transport"]["containers"][0]["number"] = bad_number
    for line in bad_container["lines"]:
        line["container_number"] = bad_number

    def quote_request(**override: Any) -> Json:
        payload = {"shipment": planned, "reply_by": None, "note": None}
        return envelope("quote_request", payload, **override)

    def submission(shipment: Json, **override: Any) -> Json:
        return envelope("document_submission", {"shipment": shipment, "note": None}, **override)

    quote = reply("artifact", "quote", payload={"shipment_id": shipment_id})
    draft = reply(
        "artifact", "declaration_draft", payload={"shipment_id": shipment_id, "mock": True}
    )
    first_reply_id = "$reply:1:message_id"

    without_reply_by = quote_request()
    del without_reply_by["payload"]["reply_by"]

    reused = quote_request()
    reused["payload"]["note"] = "Changed after the first sending."

    unexpected_quote = envelope(
        "quote",
        {
            "shipment_id": shipment_id,
            "quote_number": "Q-CONFORMANCE",
            "currency": "JPY",
            "charges": [{"name": "Freight (sample)", "amount": "1000.00"}],
            "total": "1000.00",
            "valid_until": "2026-12-31",
            "note": None,
        },
        in_reply_to="$id:other",
        role="forwarder",
    )

    cases = {
        "01_agent_card": case(
            "C01",
            "AgentCard が、プロファイルを拡張として宣言している",
            "The AgentCard declares the profile as an extension",
            [{"card": True}],
        ),
        "02_quote": case(
            "C02",
            "見積依頼に、見積を結果（Artifact）で返す",
            "A quote request is answered with a quote as an Artifact",
            [step(quote_request(), COMPLETED, quote)],
            needs=("quote_request",),
        ),
        "03_booking": case(
            "C03",
            "見積のあとのブッキング依頼に、ブッキング確認を返す",
            "A booking request after a quote is answered with a booking confirmation",
            [
                step(quote_request(), COMPLETED, quote),
                step(
                    envelope(
                        "booking_request",
                        {
                            "shipment": planned,
                            "quote_number": "$reply:1:payload.quote_number",
                            "note": None,
                        },
                        message="m2",
                        in_reply_to=first_reply_id,
                    ),
                    COMPLETED,
                    reply(
                        "artifact",
                        "booking_confirmation",
                        payload={
                            "shipment_id": shipment_id,
                            "etd": planned["transport"]["etd"],
                            "eta": planned["transport"]["eta"],
                        },
                    ),
                ),
            ],
            needs=("quote_request", "booking_request"),
        ),
        "04_discrepancy_then_draft": case(
            "C04",
            "書類の食い違いを知らせて入力待ちにし、直した再提出に申告の下書きを返す",
            "A discrepancy is reported with input required, and the corrected resubmission "
            "gets a declaration draft",
            [
                step(
                    submission(wrong),
                    INPUT_REQUIRED,
                    reply(
                        "status",
                        "discrepancy_notice",
                        payload={"shipment_id": shipment_id, "discrepancies": [discrepancy]},
                    ),
                ),
                {
                    **step(
                        submission(demo, message="m2", in_reply_to=first_reply_id), COMPLETED, draft
                    ),
                    "continue": 1,
                },
            ],
            needs=("document_submission",),
        ),
        "05_approval": case(
            "C05",
            "申告の下書きへの承認を受け付け、封筒なしで完了にする",
            "An approval of a declaration draft is accepted and completed without a reply envelope",
            [
                step(submission(demo), COMPLETED, draft),
                step(
                    envelope(
                        "approval",
                        {"shipment_id": shipment_id, "note": None},
                        message="m2",
                        in_reply_to=first_reply_id,
                    ),
                    COMPLETED,
                    None,
                ),
            ],
            needs=("document_submission", "approval"),
        ),
        "06_decline_quote": case(
            "C06",
            "見積への辞退を受け付け、封筒なしで完了にする",
            "A rejection of a quote is accepted and completed without a reply envelope",
            [
                step(quote_request(), COMPLETED, quote),
                step(
                    envelope(
                        "rejection",
                        {
                            "shipment_id": shipment_id,
                            "reason": "The quoted total is above our budget.",
                            "note": None,
                        },
                        message="m2",
                        in_reply_to=first_reply_id,
                    ),
                    COMPLETED,
                    None,
                ),
            ],
            needs=("quote_request", "rejection"),
        ),
        "07_resend": case(
            "C07",
            "同じ message_id の再送には、処理をやり直さず、最初と同じ封筒を返す",
            "A resend with the same message_id is not processed again and gets the first reply",
            [
                step(quote_request(), COMPLETED, quote),
                {"resend": 1, "expect": {"state": COMPLETED, "reply": quote, "same_reply_as": 1}},
            ],
            needs=("quote_request",),
        ),
        "08_message_id_reused": case(
            "C08",
            "同じ message_id で中身の違うメッセージは、処理せずに断る",
            "A message that reuses a message_id with different content is refused",
            [
                step(quote_request(), COMPLETED, quote),
                step(reused, REJECTED, error("MESSAGE_ID_REUSED")),
            ],
            needs=("quote_request",),
        ),
        "09_profile_version": case(
            "C09",
            "扱えないプロファイルの版は、処理せずに断る",
            "An unsupported profile version is refused without processing",
            [
                step(
                    quote_request(profile_version="9.9.9"),
                    REJECTED,
                    error(
                        "PROFILE_VERSION_UNSUPPORTED",
                        ("PROFILE_VERSION_UNSUPPORTED", "profile_version"),
                    ),
                )
            ],
        ),
        "10_unknown_profile": case(
            "C10",
            "ほかのプロファイルのメッセージは、処理せずに断る",
            "A message of another profile is refused without processing",
            [
                step(
                    quote_request(profile="other-profile"),
                    REJECTED,
                    error("PROFILE_UNKNOWN", ("PROFILE_UNKNOWN", "profile")),
                )
            ],
        ),
        "11_missing_item": case(
            "C11",
            "中身の項目が欠けていれば、箇所を示して入力待ちにする",
            "A missing item is reported with its location and the task waits for input",
            [
                step(
                    without_reply_by,
                    INPUT_REQUIRED,
                    error("VALIDATION_FAILED", ("REQUIRED_MISSING", "payload.reply_by")),
                )
            ],
            needs=("quote_request",),
        ),
        "12_invalid_shipment": case(
            "C12",
            "中の shipment が共通データ契約に合わなければ、箇所を示して入力待ちにする",
            "A shipment that breaks the shared data contract is reported with its location",
            [
                step(
                    envelope(
                        "quote_request",
                        {"shipment": bad_container, "reply_by": None, "note": None},
                    ),
                    INPUT_REQUIRED,
                    error(
                        "VALIDATION_FAILED",
                        (
                            "CONTAINER_CHECK_DIGIT",
                            "payload.shipment.transport.containers[0].number",
                        ),
                    ),
                )
            ],
            needs=("quote_request",),
        ),
        "13_not_an_envelope": case(
            "C13",
            "封筒を持たないメッセージ（文字だけ）は処理せず、誤りを知らせて入力待ちにするか、"
            "A2A のエラーで断る",
            "A message without an envelope (text only) is not processed: it is answered with an "
            "error and input required, or refused with an A2A error",
            [
                {
                    "text": "Hello",
                    "expect": {
                        "any_of": [
                            {"state": INPUT_REQUIRED, "reply": error("VALIDATION_FAILED")},
                            {"error": "CONTENT_TYPE_NOT_SUPPORTED"},
                        ]
                    },
                }
            ],
        ),
        "14_unexpected_type": case(
            "C14",
            "受け付けていない種類のメッセージは、処理せずに断る",
            "A message type the receiver does not accept is refused",
            [step(unexpected_quote, REJECTED, error("UNEXPECTED_MESSAGE"))],
            refuses=("quote",),
        ),
        "15_fix_and_continue": case(
            "C15",
            "誤りを直したメッセージを、同じタスクの続きとして受け付ける",
            "A corrected message is accepted as a continuation of the same task",
            [
                step(
                    without_reply_by,
                    INPUT_REQUIRED,
                    error("VALIDATION_FAILED", ("REQUIRED_MISSING", "payload.reply_by")),
                ),
                {**step(quote_request(message="m2"), COMPLETED, quote), "continue": 1},
            ],
            needs=("quote_request",),
        ),
        "16_extension_required": case(
            "C16",
            "必須の拡張を使うと名乗らない要求は、A2A のエラーで断る",
            "A request that does not declare the required extension is refused with an A2A error",
            [
                {
                    "send": quote_request(),
                    "without_extension": True,
                    "expect": {"error": "EXTENSION_SUPPORT_REQUIRED"},
                }
            ],
            extension_required=True,
        ),
        "17_resend_after_task_finished": case(
            "C17",
            "続きとして送ったメッセージの再送にも、タスクが終わったあとで、最初と同じ封筒を返す",
            "A resend of a message that continued a task gets the first reply, "
            "even after the task has finished",
            [
                step(
                    submission(wrong),
                    INPUT_REQUIRED,
                    reply("status", "discrepancy_notice", payload={"shipment_id": shipment_id}),
                ),
                {
                    **step(
                        submission(demo, message="m2", in_reply_to=first_reply_id), COMPLETED, draft
                    ),
                    "continue": 1,
                },
                {
                    "resend": 2,
                    "continue": 1,
                    "expect": {"state": COMPLETED, "reply": draft, "same_reply_as": 2},
                },
            ],
            needs=("document_submission",),
        ),
    }
    return cases
