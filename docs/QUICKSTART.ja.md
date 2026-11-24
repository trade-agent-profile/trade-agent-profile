# 30分でつなぐ手引き（日本語）

> **これは実験的な参照仕様です。いずれの標準化団体の公式仕様でもありません。**

判断するのは利用者です。このツールは下調べと記録を担います。

English: `QUICKSTART.en.md`　中文：`QUICKSTART.zh.md`

この手引きでは、貿易用プロファイル（trade-agent-profile）を、30分で次の順に試します。

| 手順 | やること | 目安 |
|---|---|---|
| 0 | 用意する | 10分 |
| 1 | 船積みのデータを検証する | 5分 |
| 2 | 2つのエージェントのやり取りを動かす | 5分 |
| 3 | 自分の実装を適合テストで試す | 10分 |

命令は Windows の PowerShell 向けです。1行ずつ貼って実行します。macOS や Linux では、道筋の `\` を `/` に読み替えてください。見本のデータは、すべて架空です。

## 0. 用意する（10分）

1. uv（Python の道具の管理）を、公式の手順で入れます：<https://docs.astral.sh/uv/getting-started/installation/>。入れたあとは、PowerShell を開き直します。
2. コードを取ってきて、そのフォルダに移ります。

```powershell
git clone https://github.com/trade-agent-profile/trade-agent-profile.git
```

```powershell
cd trade-agent-profile
```

3. 部品をそろえます。Python 3.12 がなければ、uv が一緒に入れます。最初の1回だけ、数分かかることがあります。

```powershell
uv sync
```

## 1. 船積みのデータを検証する（5分）

1件の船積みを1つの JSON で表したものが「共通データ契約」です（`schema/shipment.schema.json`）。正しい見本を10件まとめて調べます。

```powershell
uv run python scripts\validate.py samples\valid --lang ja
```

最後に「10件を調べました。合格 10件、不合格 0件。」と出れば成功です。

次に、合計金額が合わない見本を調べます。

```powershell
uv run python scripts\validate.py samples\invalid\05_total_mismatch.json --lang ja
```

「不合格」と出て、エラーのコード（`TOTAL_MISMATCH`）、場所（`totals.amount`）、なぜ違うか、どう直すかが表示されます。エラーは、いつもこの「コードと場所」の組で表します。

## 2. 2つのエージェントのやり取りを動かす（5分）

荷主側と、相手側（フォワーダー兼通関業者）のエージェントが、見積依頼から承認までをやり取りします。AI は使わず、決まった台本で動きます。

```powershell
uv run python scripts\demo_a2a.py
```

「やり取りしたメッセージ: 14件」と出れば成功です。2つのエージェントは A2A の通信でやり取りしますが、待ち受けるのはこのパソコンの中（127.0.0.1）だけです。記録は `reports\demo-a2a.html` にできるので、エクスプローラーでダブルクリックしてブラウザーで読みます。

記録では、1通ごとに次のことが分かります。

- どの型のメッセージか（見積依頼、見積、ブッキング、書類の提出、食い違いの通知、申告の下書き、承認 など）
- どのメッセージへの返事か
- 同じメッセージをもう一度送ったとき、相手が処理をやり直さず、最初と同じ返事を返したこと

## 3. 自分の実装を適合テストで試す（10分）

### 3.1 まず、見本の相手で試す

別の PowerShell の窓を開き、同じフォルダで、見本の相手側を待ち受けさせます（止めるときは、その窓で Ctrl+C）。

```powershell
uv run python scripts\serve_agent.py
```

もとの窓で、適合テストを実行します。

```powershell
uv run python scripts\conformance.py --target http://127.0.0.1:8027 --lang ja
```

「17件中、合格 17件」と出れば成功です。

### 3.2 自分の実装で試す

自分のエージェントを待ち受けさせ、その URL を `--target` に渡します。相手とは A2A（JSON-RPC）で通信するだけなので、何の言語で作られていても試せます。合格するために守る決まりの要点は次のとおりです。

| 決まり | 詳しくは |
|---|---|
| 1つのメッセージは、A2A の Message の Part 1つで送る。Part の `data` に封筒を入れ、`mediaType` は `application/json` | `docs/PROFILE.md` 第4節 |
| 封筒には8つの必須項目（`profile`、`profile_version`、`message_type`、`message_id`、`correlation_id`、`sent_at`、`sender`、`payload`）を入れる | 第2節 |
| AgentCard の `capabilities.extensions` で、このプロファイルの識別 URI を宣言する。必須として宣言したら、`A2A-Extensions` ヘッダでその URI を名乗らない要求は断る | 第4.1節 |
| 仕事の結果は Artifact で返す。入力を求める・断る・誤りを知らせる封筒は、状態に添える Message で返す | 第4節、第5節 |
| 同じ `message_id` が届いたら処理をやり直さず、最初と同じ返事を返す。中身が違えば `MESSAGE_ID_REUSED` で断る | 第7節 |

識別 URI は、いまは仮の値です（`docs/PROFILE.md` 第4節）。テストの一覧と、不合格の読み方は第9節にあります。

### 3.3 MCP の道具を使う（すきなときに）

検証、食い違いの一覧、申告の下書き（模擬）の3つの道具を、MCP サーバーとして AI から使えます。MCP に対応した道具に、次の起動の命令を登録します（Claude Code では、このフォルダの `.mcp.json` に登録済みです）。

```powershell
uv run python -m trade_agent_profile.mcp_server
```

## 困ったとき

- `uv` が見つからないと言われる：uv を入れたあと、PowerShell を開き直します。
- ポート 8027 がほかで使われている：`uv run python scripts\serve_agent.py --port 8028` のように番号を変え、`--target` の番号も同じにします。
- 英語だけで表示したい：`--lang en` を付けます（付けなければ日本語と英語の両方）。

## 用語

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

申告の下書きは模擬で、実際の申告には使えません。他人の依頼を受けて申告書などの通関書類を作ることを業として行うには、通関業の許可が要ります（日本の通関業法 第2条第1号ロ・第2号、第3条第1項）。税関の通達では、ほかの業務に付帯して無償で行う場合も「業として」に含まれます（通関業法基本通達 2－3）。自分の使い方が当てはまるかは、税関か専門家に確かめてください。
