# trade-agent-profile（作業中の名前）

> **これは実験的な参照仕様です。いずれの標準化団体の公式仕様でもありません。**

荷主・フォワーダー・通関業者・銀行の AI エージェントが、決まった形のデータで貿易の用件（見積、ブッキング、書類の提出、食い違いの通知、申告の下書き、承認）をやり取りするための「貿易用プロファイル」と、動く見本です。

新しい通信方式は作りません。エージェント同士の会話には A2A、道具の提供には MCP を使い、その上に載せるデータ契約・メッセージの型・命名の決まり・適合テストだけを定めます。

判断するのは利用者です。このツールは下調べと記録を担います。

## いまできること

- 1件の船積みを1つの JSON で表す「共通データ契約 v0.1.0」（`schema/shipment.schema.json`）
- その JSON を調べる検証コマンド。エラーは日本語と英語で「どの項目が・なぜ違うか・どう直すか」を示します
- 架空の見本 20件（正しい例 10件、誤り例 10件と、その期待結果）
- ほかのプロジェクトへ渡す配布物（`dist/contract-v0.1/`）
- メッセージの外枠（封筒）と10種類の型（`schema/message.schema.json`）。仕様は `docs/PROFILE.md`
- 台本デモ：荷主側と相手側が、見積依頼から承認までをやり取りし、記録を HTML に出します（AI は使いません）
- A2A のエージェント2つ（荷主側と相手側）。同じ台本を、実際の A2A の通信でやり取りします（このパソコンの中だけ）
- 適合テスト 17件。ほかの人が作った実装が、決まりどおりに答えるかを確かめられます
- MCP サーバー。検証、食い違いの一覧、申告の下書き（模擬）の3つの道具を、AI から使えます
- 公開前の検査。鍵やパスワードの形、メールアドレス、電話番号、パソコンの利用者名などが入っていないかを、git の履歴まで含めて機械で調べます（`scripts/prepublish_check.py`）

30分でつなぐ手引きは `docs/QUICKSTART.ja.md`（English: `docs/QUICKSTART.en.md`、中文：`docs/QUICKSTART.zh.md`）、既存の標準との対応表は `docs/MAPPING.md`、設計の考え方は `docs/RATIONALE.md` にあります。

## 使い方

PowerShell でこのフォルダに移り、1行ずつ実行します。最初の1回だけ、部品をそろえます。

```powershell
uv sync
```

正しい見本を調べる（10件すべて合格になります）。

```powershell
uv run python scripts\validate.py samples\valid
```

誤りの見本を調べる（10件すべて不合格になり、理由と直し方が出ます）。

```powershell
uv run python scripts\validate.py samples\invalid
```

自分のファイルを調べる。ファイル、フォルダ、複数のファイル、ワイルドカード（`*`）のどれでも渡せます。

```powershell
uv run python scripts\validate.py samples\valid\*.json
```

| 付けられる指定 | 働き |
|---|---|
| `--lang ja` | 日本語だけで表示する（`en` なら英語だけ。指定しなければ両方） |
| `--json` | 結果を、ほかのプログラムで読める JSON で出す |
| `--quiet` | 問題のあるファイルと集計だけを出す |
| `--expected` | 対になる `.expected.json` と比べる（誤り例の確認用） |

全部まとめて確かめる（Ruff → テスト → 見本の検証 → 公開前の検査 → 適合テスト）。1分ほどかかります。最後の行に `CHECK OK` と出れば合格です。

```powershell
uv run python scripts\check.py
```

台本デモを実行する（見積依頼から承認まで）。終わると、記録が `reports\demo.html` にできます。エクスプローラーでダブルクリックすると、ブラウザーで読めます。

```powershell
uv run python scripts\demo.py
```

メッセージの見本を調べる（10種類の型が1件ずつあり、すべて合格になります）。

```powershell
uv run python scripts\validate.py samples\messages
```

同じ台本を、2つのエージェントの A2A の通信で実行する。通信は、このパソコンの中だけで行います。記録は `reports\demo-a2a.html` にできます。

```powershell
uv run python scripts\demo_a2a.py
```

適合テストを、この見本の実装で試す（相手側のエージェントを自動で起動し、17件を実行して、終わったら止めます）。

```powershell
uv run python scripts\conformance.py --self-test --lang ja
```

### 自分の実装を、適合テストで試す

試したいエージェントを起動しておき、その URL を渡します。相手とは A2A で通信するだけなので、何の言語で作られていても試せます。

```powershell
uv run python scripts\conformance.py --target http://127.0.0.1:8027
```

試す相手として、この見本の相手側を起動しておくこともできます。別の PowerShell の窓で次を実行します（止めるときは、その窓で Ctrl+C を押します）。

```powershell
uv run python scripts\serve_agent.py
```

テストの中身（送るものと、期待する答え）は `conformance\cases\` に JSON で置いてあります。一覧と読み方は `docs\PROFILE.md` の第9節にあります。

### MCP の道具を使う

Claude Code で、このフォルダの新しいチャットを開くと、`.mcp.json` に登録した MCP サーバー（trade-agent-profile）が読み込まれます。使ってよいかの確認が出たら、許可します。道具は3つです。

| 道具 | 働き |
|---|---|
| `validate` | shipment.json かメッセージを検証する |
| `list_discrepancies` | 書類の値と正本の食い違いを一覧にする |
| `draft_declaration` | 申告の下書き（模擬）を作る。実際の申告ではありません |

たとえば Claude Code に「samples\valid\01_sea_fob_1c_1l.json を trade-agent-profile の validate で検証して」と頼みます。道具は規則だけで動き、AI は使いません。渡されたデータを確かめるだけで、外部には何も送りません。

MCP の公式の部品でつないで3つの道具を呼べることは、テストで確かめてあります。Claude Code の画面からの呼び出しも、このフォルダで新しく開いたチャット（デスクトップアプリの Code タブ）で確かめました（2026-11-22）。`validate` に見本を2件渡したところ、`samples\valid\01_sea_fob_1c_1l.json` は合格、`samples\invalid\05_total_mismatch.json` はコード `TOTAL_MISMATCH`（場所 `totals.amount`）の誤りで不合格となり、どちらも期待どおりでした。

## 検証で分かること・分からないこと

- 分かること：項目の過不足、型、コードや日付の形式、コンテナ番号の検査数字（ISO 6346）、明細の合計と総額の一致、日付の前後、書類の値と正本の食い違いが記録されているか。
- 分からないこと：国・通貨・港・単位・包装のコードが実在するかどうか（v0.1 は形式だけを調べます）。品目番号や規制への適合も判断しません。
- 見本はすべて架空です。形の例であり、実際の取引や規制への適合を示すものではありません。
- 申告の下書きは模擬で、実際の申告には使えません。他人の依頼を受けて申告書などの通関書類を作ることを業として行うには、通関業の許可（財務大臣）が要ります（通関業法 第2条第1号ロ・第2号、第3条第1項）。自分の使い方が当てはまるかは、税関か専門家に確かめてください。

## フォルダの案内

| 場所 | 中身 |
|---|---|
| `schema/` | 共通データ契約とメッセージの正本（スキーマ） |
| `samples/` | 架空の見本（`valid/`、`invalid/`、`messages/`） |
| `conformance/cases/` | 適合テストの入力と期待出力（17件） |
| `reports/` | 台本デモの記録（`demo.html`。A2A で実行した記録は `demo-a2a.html`） |
| `src/trade_agent_profile/` | 検証のライブラリとコマンド、A2A のエージェント、MCP サーバー |
| `scripts/` | 入口になる命令（`validate.py`、`check.py`、`conformance.py` など） |
| `tests/` | テスト |
| `dist/contract-v0.1/` | ほかのプロジェクトへ渡す配布物 |
| `docs/` | 仕様、手引き、対応表、設計の考え方などの文書 |

## 困ったとき

### uv と Python 3.12 を元に戻す（消す）

このプロジェクトのために入れたのは、uv（道具の管理）と、uv が管理する Python 3.12 だけです。もともと入っていた Python には触っていません。消すときは、uv の公式の手順（<https://docs.astral.sh/uv/getting-started/installation/#uninstallation>）に従います。

## 文書

- `docs/PROFILE.md`：仕様の本体（封筒、10種類の型、A2A への載せ方、状態・版・再送の扱い、適合テスト、MCP の道具）
- `docs/MAPPING.md`：既存の標準（DCSA、TradeTrust など）との対応表
- `docs/QUICKSTART.ja.md`、`.en.md`、`.zh.md`：30分でつなぐ手引き（日本語・英語・中国語）
- `docs/RATIONALE.md`：設計の考え方と、採らなかった案
- `docs/EVAL.md`：見本に対する正解数
- `docs/CONTRACT_PROPOSALS.md`：共通データ契約への提案

## ライセンス

- コード、スキーマ（`schema/`）、見本（`samples/`）、適合テスト（`conformance/`）、配布物（`dist/`）：Apache License 2.0（`LICENSE`）
- 文書（この README、`docs/` の文書、手引き）：クリエイティブ・コモンズ 表示 4.0 国際（CC BY 4.0。`LICENSE-DOCS.md`）

提案のしかたは `CONTRIBUTING.md`、セキュリティの問題の知らせ方は `SECURITY.md` にあります。
