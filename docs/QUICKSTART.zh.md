# 30 分钟上手指南（中文）

> **这是实验性的参考规范，不是任何标准化组织的正式规范。**

判断由使用者做出。本工具只负责前期核查和记录。

日本語：`QUICKSTART.ja.md`　English：`QUICKSTART.en.md`

本指南用 30 分钟，按下面的顺序试用贸易 profile（trade-agent-profile）。

| 步骤 | 内容 | 大约时间 |
|---|---|---|
| 0 | 准备 | 10 分钟 |
| 1 | 校验装运数据 | 5 分钟 |
| 2 | 运行两个智能体之间的往来 | 5 分钟 |
| 3 | 用一致性测试检验自己的实现 | 10 分钟 |

命令面向 Windows 的 PowerShell，请逐行粘贴执行。在 macOS 或 Linux 上，请把路径中的 `\` 换成 `/`。样例数据全部是虚构的。工具的显示语言是日语和英语；加上 `--lang en` 只显示英语。

## 0. 准备（10 分钟）

1. 按官方步骤安装 uv（Python 工具的管理器）：<https://docs.astral.sh/uv/getting-started/installation/>。安装后请重新打开 PowerShell。
2. 获取代码，并进入该文件夹。

```powershell
git clone https://github.com/trade-agent-profile/trade-agent-profile.git
```

```powershell
cd trade-agent-profile
```

3. 准备依赖组件。如果没有 Python 3.12，uv 会一并安装。第一次可能需要几分钟。

```powershell
uv sync
```

## 1. 校验装运数据（5 分钟）

"共享数据契约"用一个 JSON 表示一票货物的装运（`schema/shipment.schema.json`）。先一次检查 10 个正确的样例。

```powershell
uv run python scripts\validate.py samples\valid --lang en
```

最后一行显示 "Checked 10 file(s): 10 valid, 0 invalid." 即为成功。

接着检查一个总金额与明细不一致的样例。

```powershell
uv run python scripts\validate.py samples\invalid\05_total_mismatch.json --lang en
```

结果为不合格（invalid），并显示错误代码（`TOTAL_MISMATCH`）、位置（`totals.amount`）、原因和修改方法。错误始终用"代码 + 位置"这一组来表示。

## 2. 运行两个智能体之间的往来（5 分钟）

托运人一方的智能体，与对方（兼任货运代理和报关行）的智能体，从询价到最终批准进行往来。不使用 AI，按固定的脚本运行。

```powershell
uv run python scripts\demo_a2a.py
```

运行结束时，会用日语显示简短的汇总，最后一行是记录文件的位置 `reports\demo-a2a.html`。两个智能体通过 A2A 通信，但只在本机（127.0.0.1）上监听。在资源管理器中双击记录文件，即可在浏览器中阅读。

记录中可以看到每一条消息的以下内容：

- 消息类型（询价、报价、订舱、提交单证、不符点通知、报关单草稿、批准等）
- 是对哪一条消息的回复
- 同一条消息再次发送时，对方没有重复处理，而是返回与第一次相同的回复

## 3. 用一致性测试检验自己的实现（10 分钟）

### 3.1 先用样例对方来试

另开一个 PowerShell 窗口，在同一个文件夹中让样例对方开始监听（停止时在该窗口按 Ctrl+C）。

```powershell
uv run python scripts\serve_agent.py
```

回到原来的窗口，运行一致性测试。

```powershell
uv run python scripts\conformance.py --target http://127.0.0.1:8027 --lang en
```

显示 "17 test(s): 17 passed, 0 failed, 0 skipped" 即为成功。

### 3.2 用自己的实现来试

让自己的智能体开始监听，把它的 URL 传给 `--target`。测试只通过 A2A（JSON-RPC）与对方通信，所以用任何语言实现都可以测试。要通过测试，需要遵守下面的要点（`docs/PROFILE.md` 目前只有日文版）。

| 规则 | 详见 |
|---|---|
| 一条消息用 A2A Message 的一个 Part 发送。把信封放进 Part 的 `data`，`mediaType` 设为 `application/json` | `docs/PROFILE.md` 第 4 节 |
| 信封有 8 个必填项：`profile`、`profile_version`、`message_type`、`message_id`、`correlation_id`、`sent_at`、`sender`、`payload` | 第 2 节 |
| 在 AgentCard 的 `capabilities.extensions` 中声明本 profile 的标识 URI。如果声明为必需，对于没有在 `A2A-Extensions` 头中写明该 URI 的请求，要予以拒绝 | 第 4.1 节 |
| 工作结果用 Artifact 返回。要求补充信息、拒绝或报告错误的信封，用附在任务状态上的 Message 返回 | 第 4 节、第 5 节 |
| 收到相同的 `message_id` 时不重复处理，返回与第一次相同的回复。如果内容不同，用 `MESSAGE_ID_REUSED` 拒绝 | 第 7 节 |

标识 URI 目前是临时值（`docs/PROFILE.md` 第 4 节）。测试一览和不合格结果的读法见第 9 节。

### 3.3 使用 MCP 工具（可选）

校验、不符点一览、报关单草稿（模拟）这三个工具，可以通过 MCP 服务器提供给 AI 使用。请在支持 MCP 的应用中登记下面的启动命令（Claude Code 已在本文件夹的 `.mcp.json` 中登记）。

```powershell
uv run python -m trade_agent_profile.mcp_server
```

## 遇到问题时

- 提示找不到 `uv`：安装 uv 后，请重新打开 PowerShell。
- 端口 8027 已被占用：像 `uv run python scripts\serve_agent.py --port 8028` 这样换一个端口号，`--target` 也使用同一个端口号。
- 只想看英语显示：加上 `--lang en`（不加时同时显示日语和英语）。

## 用语

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

报关单草稿是模拟的，不能用于实际申报。在日本，接受他人委托、以营业为目的制作申报单等报关单证，需要取得通关业许可（日本《通关业法》第2条第1号ロ・第2号、第3条第1項）。
