"""プロファイルの名前・版と、A2A に載せるときに使う決まった値。

A2A の用語と節番号は、仕様 1.0.0（2026-11-22 に原文を確認）による。
"""

from __future__ import annotations

PROFILE = "trade-agent-profile"
PROFILE_VERSION = "0.1.0"
SUPPORTED_PROFILE_VERSIONS = ("0.1.0",)

# A2A の拡張として AgentCard で宣言するときの識別 URI（A2A 4.6.1、4.6.3）。
# 公開する場所が決まるまでの仮の値で、M4 で確定する。.invalid は実在しない宛先。
PROFILE_URI = "https://trade-agent-profile.github.io/v0.1"

# 封筒を A2A の Part に載せるときの種類（A2A 4.1.6）
MEDIA_TYPE = "application/json"

MESSAGE_TYPES = (
    "quote_request",
    "quote",
    "booking_request",
    "booking_confirmation",
    "document_submission",
    "discrepancy_notice",
    "declaration_draft",
    "approval",
    "rejection",
    "error",
)
SENDER_ROLES = ("shipper", "forwarder", "customs_broker", "bank")

# 仕事の結果として返す型。A2A では Artifact で返す（A2A 3.7、4.1.7）
RESULT_TYPES = ("quote", "booking_confirmation", "declaration_draft")
# 状態に添えて返す型。A2A では TaskStatus の message に入れる（A2A 3.7、4.1.2）
STATUS_TYPES = ("discrepancy_notice", "rejection", "error")
# どのメッセージへの返事かを、in_reply_to で必ず示す型
REPLY_TYPES = (
    "quote",
    "booking_confirmation",
    "discrepancy_notice",
    "declaration_draft",
    "approval",
    "rejection",
)

# A2A のタスクの状態（A2A 4.1.3）
SUBMITTED = "TASK_STATE_SUBMITTED"
WORKING = "TASK_STATE_WORKING"
COMPLETED = "TASK_STATE_COMPLETED"
FAILED = "TASK_STATE_FAILED"
CANCELED = "TASK_STATE_CANCELED"
INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
REJECTED = "TASK_STATE_REJECTED"
AUTH_REQUIRED = "TASK_STATE_AUTH_REQUIRED"

TASK_STATES = (
    SUBMITTED,
    WORKING,
    COMPLETED,
    FAILED,
    CANCELED,
    INPUT_REQUIRED,
    REJECTED,
    AUTH_REQUIRED,
)
# 終わった状態。ここからは、同じタスクに続きを送れない（A2A 3.1.1）
TERMINAL_STATES = (COMPLETED, FAILED, CANCELED, REJECTED)
