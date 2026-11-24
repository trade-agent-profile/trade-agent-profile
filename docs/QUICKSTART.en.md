# 30-minute quickstart (English)

> **This is an experimental reference specification. It is not an official specification of any standards body.**

The user makes the decisions. This tool only helps with preliminary checks and record keeping.

日本語：`QUICKSTART.ja.md`　中文：`QUICKSTART.zh.md`

This guide lets you try the trade profile (trade-agent-profile) in 30 minutes, in this order.

| Step | What you do | Time |
|---|---|---|
| 0 | Get ready | 10 min |
| 1 | Validate shipment data | 5 min |
| 2 | Run an exchange between two agents | 5 min |
| 3 | Test your own implementation with the conformance tests | 10 min |

The commands are for Windows PowerShell. Paste and run them one line at a time. On macOS or Linux, read `\` in paths as `/`. All sample data is fictitious. The tools display Japanese and English; add `--lang en` to show English only.

## 0. Get ready (10 min)

1. Install uv (a manager for Python tools) by following the official instructions: <https://docs.astral.sh/uv/getting-started/installation/>. Open PowerShell again after installing.
2. Get the code and move into its folder.

```powershell
git clone https://github.com/trade-agent-profile/trade-agent-profile.git
```

```powershell
cd trade-agent-profile
```

3. Install the dependencies. If Python 3.12 is missing, uv installs it too. The first run can take a few minutes.

```powershell
uv sync
```

## 1. Validate shipment data (5 min)

The "shared data contract" describes one shipment as one JSON document (`schema/shipment.schema.json`). Check the ten valid samples at once.

```powershell
uv run python scripts\validate.py samples\valid --lang en
```

It worked if the last line says "Checked 10 file(s): 10 valid, 0 invalid."

Next, check a sample whose total amount does not match its lines.

```powershell
uv run python scripts\validate.py samples\invalid\05_total_mismatch.json --lang en
```

It is reported as invalid, with the error code (`TOTAL_MISMATCH`), the location (`totals.amount`), why it is wrong, and how to fix it. An error is always identified by this pair of a code and a location.

## 2. Run an exchange between two agents (5 min)

An agent on the shipper's side and an agent on the other side (a freight forwarder that is also a customs broker) exchange messages from a quote request to the final approval. No AI is used; they follow a fixed script.

```powershell
uv run python scripts\demo_a2a.py
```

When it finishes, it prints a short summary in Japanese that ends with the path of the record, `reports\demo-a2a.html`. The two agents talk over A2A, but they listen only on this computer (127.0.0.1). Double-click the record in File Explorer to read it in a browser.

For each message, the record shows:

- its type (quote request, quote, booking, document submission, discrepancy notice, declaration draft, approval, and so on)
- which message it answers
- that when the same message is sent again, the other side does not process it again and returns the same answer as the first time

## 3. Test your own implementation with the conformance tests (10 min)

### 3.1 First, try it against the reference agent

Open another PowerShell window in the same folder and start the reference agent of the other side (press Ctrl+C in that window to stop it).

```powershell
uv run python scripts\serve_agent.py
```

In the first window, run the conformance tests.

```powershell
uv run python scripts\conformance.py --target http://127.0.0.1:8027 --lang en
```

It worked if it says "17 test(s): 17 passed, 0 failed, 0 skipped".

### 3.2 Try it against your own implementation

Start your own agent and pass its URL to `--target`. The tests only talk to it over A2A (JSON-RPC), so it can be written in any language. To pass, follow these rules (`docs/PROFILE.md` is currently available in Japanese only).

| Rule | Details |
|---|---|
| Send each message as exactly one Part of an A2A Message. Put the envelope in the Part's `data`, with `mediaType` set to `application/json` | `docs/PROFILE.md` section 4 |
| Every envelope has eight required fields: `profile`, `profile_version`, `message_type`, `message_id`, `correlation_id`, `sent_at`, `sender`, `payload` | section 2 |
| Declare the profile's identifier URI in the AgentCard's `capabilities.extensions`. If you declare it as required, reject requests that do not name that URI in the `A2A-Extensions` header | section 4.1 |
| Return results of work as Artifacts. Return envelopes that ask for input, refuse, or report an error as the Message attached to the task status | sections 4 and 5 |
| When the same `message_id` arrives again, do not process it again; return the same answer as the first time. If the content differs, refuse with `MESSAGE_ID_REUSED` | section 7 |

The identifier URI is a provisional value for now (`docs/PROFILE.md` section 4). The list of tests and how to read failures are in section 9.

### 3.3 Use the MCP tools (optional)

Three tools (validation, a list of discrepancies, and a mock declaration draft) are available to AI applications through an MCP server. Register the following start command in an MCP-capable application (for Claude Code, it is already registered in this folder's `.mcp.json`).

```powershell
uv run python -m trade_agent_profile.mcp_server
```

## Troubleshooting

- `uv` is not found: open PowerShell again after installing uv.
- Port 8027 is already in use: change the number, as in `uv run python scripts\serve_agent.py --port 8028`, and use the same number in `--target`.
- You want English only: add `--lang en` (without it, both Japanese and English are shown).

## Terms

| 日本語 | English | 中文 |
|---|---|---|
| 共通データ契約 | shared data contract | 共享数据契约 |
| 封筒 | envelope | 信封 |
| メッセージの型 | message type | 消息类型 |
| 検証 | validation | 校验 |
| 適合テスト | conformance test | 一致性测试 |
| 識別 URI | identifier URI | 标识 URI |
| 再送 | resend | 重发 |
| 正本の値 | authoritative value | 权威值 |
| 食い違い | discrepancy | 不符点 |
| 申告の下書き（模擬） | declaration draft (mock) | 报关单草稿（模拟） |
| 荷主 | shipper | 托运人 |
| フォワーダー | freight forwarder | 货运代理 |
| 通関業者 | customs broker | 报关行 |

The declaration draft is a mock and cannot be used for an actual declaration. In Japan, preparing customs documents such as declarations for others as a business requires a customs brokerage license (Customs Brokerage Act, Article 2, item 1 (b) and item 2, and Article 3, paragraph 1). According to the Japan Customs circular on this Act (2-3), "as a business" also covers work done free of charge alongside another business. Ask customs or a qualified professional whether your use falls under this.
