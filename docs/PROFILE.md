# 貿易用プロファイル（trade-agent-profile）仕様 v0.1.0

> **これは実験的な参照仕様です。いずれの標準化団体の公式仕様でもありません。**

判断するのは利用者です。このツールは下調べと記録を担います。

- 状態：v0.1.0（実験的）。手引きは `docs/QUICKSTART.ja.md`（英語・中国語もある）、既存の標準との対応表は `docs/MAPPING.md`、設計の考え方は `docs/RATIONALE.md`。
- 版：プロファイル 0.1.0。共通データ契約は 0.1.0 を基準とし、項目を足した 0.1.1 のデータも運べる（第6節）
- A2A の用語と節番号は、A2A 仕様 1.0.0 の原文（2026-11-22 に確認）による。A2A の本文は転載していない。
- 見本の実装が使っている公式の部品（どちらも Python 用）：a2a-sdk 1.3.1、mcp 2.3.0

## 1. 何を定めるか

荷主・フォワーダー・通関業者・銀行の AI エージェントが、貿易の用件を決まった形のデータでやり取りするための取り決めである。新しい通信方式は作らない。

| 定めるもの | 置き場所 |
|---|---|
| 1件の船積みを表すデータ（共通データ契約） | `schema/shipment.schema.json`、読み方は `dist/contract-v0.1/README.ja.md` |
| メッセージの外枠（封筒）と10種類の型 | `schema/message.schema.json`、この文書の第2〜3節 |
| A2A への載せ方、状態の対応、版と再送の扱い | この文書の第4〜7節 |
| 適合テスト（ほかの実装が決まりどおりかを確かめる） | `conformance/cases/`、この文書の第9節 |
| MCP の道具（検証、食い違いの一覧、申告の下書き（模擬）） | この文書の第10節 |

定めないもの：通信方式そのもの（A2A と MCP に従う）、認証、料金や業務の判断。

## 2. 封筒

どのメッセージも、次の封筒に入れて送る。

| 項目 | 必須 | 形式 | 意味 |
|---|---|---|---|
| `profile` | 必須 | `trade-agent-profile` | このプロファイルのメッセージであることを示す |
| `profile_version` | 必須 | 例 `0.1.0` | プロファイルの版 |
| `message_type` | 必須 | 第3節の10種類のどれか | メッセージの種類 |
| `message_id` | 必須 | UUID（英小文字） | メッセージごとに新しく振る。二重処理を防ぐ識別子として使う |
| `correlation_id` | 必須 | UUID（英小文字） | 1件の船積みについての会話を束ねる。最初の送り手が振り、返事も同じ値を使う |
| `in_reply_to` | 任意 | UUID か null | どのメッセージへの返事か。返事の型（第3節）では必須 |
| `sent_at` | 必須 | 時差つきの日時 | 送った日時（例 `2026-12-01T09:00:00+09:00`） |
| `sender` | 必須 | `role`・`name`・`id` | 送り手。`role` は、そのメッセージでの立場（`shipper`・`forwarder`・`customs_broker`・`bank`） |
| `payload` | 必須 | オブジェクト | 種類ごとの中身（第3節） |

決まり：

- 省けるのは `in_reply_to` だけ。ほかの項目と、中身（payload）の項目は省けない。分からない値は、null にできる項目に限り null と書く。
- 封筒にも中身にも、決められていない項目は足せない。
- 中身に `shipment` がある型では、その `shipment` は共通データ契約（shipment.json）にも合っていなければならない。契約のどの版の形で調べるかは、`shipment` の中の `contract_version` で決まる（第6節）。

## 3. 10種類の型

「返事」の欄が「必須」の型は、`in_reply_to` に相手のメッセージの `message_id` を書く。

| 型 | だれが送るか（見本の場合） | 用件 | 返事 | 受け手が返すもの |
|---|---|---|---|---|
| `quote_request` | 荷主 → フォワーダー | 見積を頼む | — | `quote` |
| `quote` | フォワーダー → 荷主 | 見積を返す | 必須 | — |
| `booking_request` | 荷主 → フォワーダー | ブッキングを頼む | 任意 | `booking_confirmation` |
| `booking_confirmation` | フォワーダー → 荷主 | ブッキングの番号と日程を返す | 必須 | — |
| `document_submission` | 荷主 → 通関業者 | 書類から読み取った値をつけて、船積みのデータを出す | 任意 | `declaration_draft` か `discrepancy_notice` |
| `discrepancy_notice` | 通関業者 → 荷主 | 書類の値と正本の食い違いを知らせ、直すよう求める | 必須 | — |
| `declaration_draft` | 通関業者 → 荷主 | 申告の下書き（模擬）を返す | 必須 | — |
| `approval` | 荷主 → 通関業者 | 内容を確かめて承認する | 必須 | なし |
| `rejection` | どちらからでも | 断る（理由を添える） | 必須 | なし |
| `error` | どちらからでも | 処理できなかったことを知らせる | 任意 | なし |

### 中身（payload）の項目

「null 可」と書いていない項目は、null にできない。

| 型 | 項目 |
|---|---|
| `quote_request` | `shipment`（船積みのデータ）、`reply_by`（回答の期限。日付、null 可）、`note`（null 可） |
| `quote` | `shipment_id`、`quote_number`、`currency`、`charges`（1件以上。`name` と `amount`）、`total`（料金の合計と一致すること）、`valid_until`（日付）、`note`（null 可） |
| `booking_request` | `shipment`、`quote_number`、`note`（null 可） |
| `booking_confirmation` | `shipment_id`、`booking_number`、`etd`、`eta`（`etd` より前にできない）、`cargo_cutoff_at`（日時、null 可）、`note`（null 可） |
| `document_submission` | `shipment`、`note`（null 可） |
| `discrepancy_notice` | `shipment_id`、`discrepancies`（1件以上。`doc_type`、`doc_number`（null 可）、`path`、`document_value`、`authoritative_value`）、`note`（null 可） |
| `declaration_draft` | `shipment_id`、`draft_number`、`mock`（必ず true）、`exporter`、`consignee`、`port_of_loading`、`port_of_discharge`、`etd`（null 可）、`incoterms`、`currency`、`invoice_amount`（明細の金額の合計と一致すること）、`lines`（1件以上）、`unverified`（出典で確かめていない項目の一覧）、`note`（null 可） |
| `approval` | `shipment_id`、`note`（null 可） |
| `rejection` | `shipment_id`（null 可）、`reason`、`note`（null 可） |
| `error` | `code`（下の表）、`text`（`ja` と `en`）、`issues`（`code` と `path` の一覧。0件可） |

`error` の `code`：

| コード | 意味 |
|---|---|
| `PROFILE_UNKNOWN` | このプロファイルのメッセージではない |
| `PROFILE_VERSION_UNSUPPORTED` | プロファイルの版が合わない |
| `VALIDATION_FAILED` | 内容に不足か誤りがある（`issues` に箇所を並べる） |
| `MESSAGE_ID_REUSED` | 同じ `message_id` で、中身の違うメッセージが届いた |
| `UNEXPECTED_MESSAGE` | 受け手が受け付けていない種類のメッセージ |
| `INTERNAL_ERROR` | 受け手の側の想定外の失敗 |

`document_submission` の特例：中の `shipment` で、書類の値が正本と違うのに記録がない場合（共通データ契約では `DISCREPANCY_NOT_RECORDED`）は、メッセージの検証ではエラーにしない。受け手が `discrepancy_notice` で答えるためである。

申告の下書きについて：`declaration_draft` は、データの流れを示すための模擬である。実際の申告ではなく、正本の値を写すだけで、品目番号などの判断はしない。出典で確かめていない値は `unverified` に並べる。

## 4. A2A への載せ方

| このプロファイル | A2A | A2A の節 |
|---|---|---|
| 1つのメッセージ | Message の Part 1つ。`data` に封筒、`mediaType` は `application/json` | 4.1.4、4.1.6 |
| `message_id` | Message の `messageId` に同じ値を入れる | 4.1.4、3.3.1 |
| `correlation_id` | 封筒の中だけで持つ。A2A の `contextId` は受け手が振った値を使い、同じ会話の続きでは送り手がその値を付ける | 3.4.1 |
| 受け付けた1件の仕事 | Task。識別子は受け手が振る。入力待ちのタスクには、`taskId` を付けて続きを送る | 3.4.2、4.1.1、3.1.1 |
| 仕事の結果（`quote`、`booking_confirmation`、`declaration_draft`） | Artifact で返す（Part 1つ、`data` に封筒） | 3.7、4.1.7 |
| 入力を求める・断る・誤りを知らせる封筒（`discrepancy_notice`、`rejection`、`error`） | TaskStatus の `message` に入れて返す | 3.7、4.1.2 |
| 返事の封筒の `message_id` | Artifact なら `artifactId` に、状態に添える Message なら `messageId` に、同じ値を入れる。Artifact の `name` には `message_type` を入れる | 4.1.4、4.1.7 |
| 受け手の判断 | TaskState（第5節） | 4.1.3 |
| プロファイルを扱えることの宣言 | AgentCard の `capabilities.extensions` に、識別 URI を持つ AgentExtension を書く（4.1） | 4.4.3、4.4.4、4.6.1 |
| プロファイルを使う合図 | 要求の `A2A-Extensions` ヘッダと、Message・Artifact の `extensions` に識別 URI を書く | 3.2.6、4.6.1、4.6.2、14.2.2 |
| AgentCard の置き場所と、つなぎ方 | AgentCard は決まった場所（`/.well-known/agent-card.json`）に置く。見本の実装のつなぎ方は JSON-RPC（HTTP の上） | 8.2、8.3.1、9.1 |

識別 URI は `https://trade-agent-profile.github.io/v0.1` である。A2A は、拡張の URI に版を入れ、意味が変わるときは新しい URI にすることを求め、拡張の仕様をその URI に置くことを勧めている（A2A 4.6）。この住所には、公開のあとで仕様を置く。共通データ契約とメッセージのスキーマの `$id` も、同じ住所の下にそろえてある（`.../v0.1/shipment.schema.json`、`.../v0.1/message.schema.json`）。

`correlation_id` を A2A の `contextId` と別にしている理由：A2A では、送り手が自分で決めた `contextId` を付けることは、受け手の扱いが分かっている場合を除いて勧められていない（3.4.1）。会話を束ねる値を確実に運ぶため、封筒の中に持つ。

### 4.1 AgentCard での宣言

プロファイルを扱えるエージェントは、AgentCard の `capabilities.extensions` に次の形の宣言を1つ入れる（値は見本の相手側のもの）。

```json
{
  "uri": "https://trade-agent-profile.github.io/v0.1",
  "required": true,
  "params": {
    "profile": "trade-agent-profile",
    "profile_versions": ["0.1.0"],
    "roles": ["forwarder", "customs_broker"],
    "accepts": ["quote_request", "booking_request", "document_submission", "approval", "rejection"]
  }
}
```

| 項目 | 意味 |
|---|---|
| `uri` | このプロファイルの識別 URI |
| `required` | このプロファイルのメッセージしか受け付けないエージェントは `true` にする |
| `params.profile` | 封筒の `profile` と同じ名前 |
| `params.profile_versions` | 扱える `profile_version` の一覧 |
| `params.roles` | このエージェントが担う立場（封筒の `sender.role` と同じ言葉） |
| `params.accepts` | 引き受けるメッセージの型の一覧。送るだけで何も引き受けないなら、空の一覧にする |

- `required` を `true` と宣言したエージェントは、要求の `A2A-Extensions` ヘッダに識別 URI がないとき、処理をせずに A2A の ExtensionSupportRequiredError を返す（A2A 3.3.4。JSON-RPC ではコード -32008。5.4）。
- 送り手は、相手の AgentCard を読み、`accepts` にない型は送らない。`accepts` にない型が届いたとき、受け手は `error`（`UNEXPECTED_MESSAGE`）で断る（第5節）。
- 見本の実装は、少しずつ返す方式（ストリーミング）と、あとから知らせる方式（プッシュ通知）を使わないので、`capabilities` のどちらも `false` と宣言している。

### 4.2 封筒でないメッセージ

受け手は、Part がちょうど1つで、その Part が `data` を持つときだけ、封筒として読む。それ以外（文字だけのメッセージ、Part が2つ以上あるメッセージ）は処理をしない。答え方は、次のどちらでもよい。

- タスクを `TASK_STATE_INPUT_REQUIRED` にして、`error`（`VALIDATION_FAILED`）を添える（見本の実装はこちら）。
- A2A の ContentTypeNotSupportedError を返す（AgentCard に書いた種類 `application/json` 以外を受け付けない、という A2A の決まりどおりの答え方。3.1.1）。

### 4.3 数の扱い

A2A の Part の `data` は JSON の値を運ぶ（4.1.6）。見本が使っている公式の部品では、数はすべて倍精度の小数として運ばれ、たとえば 18 は 18.0 になって届く。そのため、次のように決める。

- 受け手は、小数部が 0 の数を整数として扱う（18.0 は 18 と同じ）。
- 「中身が同じ」かどうか（第7節）は、JSON の値として比べる。18 と 18.0 は同じ数である。
- 金額・数量・重量を文字列で持つという共通データ契約の決まりは、ここでも効いている（桁の多い数を、途中で丸められずに運べる）。数のまま持つのは、行番号・ページ・確からしさ・紙面上の位置のように、桁の少ないものだけである。

### 4.4 見本の2つの動かし方

| 命令 | 何をするか | 記録 |
|---|---|---|
| `uv run python scripts\demo.py` | 通信をせず、1つのプログラムの中で封筒を受け渡す。何度実行しても同じ記録になる | `reports/demo.html` |
| `uv run python scripts\demo_a2a.py` | 荷主側と相手側の2つのエージェントを起動し、同じ台本を実際の A2A の通信でやり取りする。待ち受けは、このパソコンの中だけ（127.0.0.1） | `reports/demo-a2a.html` |

2つの記録は、振られる識別子（タスクとメッセージ）の値が違うだけで、やり取りの中身と、返事がどのメッセージを指すかの関係は同じである（テストで確かめている）。A2A の方では、荷主側は送る役（A2A のクライアント）で、自分の AgentCard も置くが、この台本では何も引き受けない。

## 5. 状態の対応

受け手は、受け付けた結果を A2A のタスクの状態で示す。

| 受け手の判断 | 返す封筒 | A2A のタスクの状態 | そのあと |
|---|---|---|---|
| 受け付けて処理し、結果を返す | `quote`・`booking_confirmation`・`declaration_draft`（Artifact） | `TASK_STATE_COMPLETED` | タスクは終わり |
| 受け付けて処理したが、返す結果がない（`approval` や `rejection` を受け取った） | なし | `TASK_STATE_COMPLETED` | タスクは終わり |
| 内容に不足や誤りがあり、直せば続けられる | `error`（`VALIDATION_FAILED`） | `TASK_STATE_INPUT_REQUIRED` | 直したメッセージを、新しい `message_id` で、同じタスクの続きとして送る |
| 書類の値が正本と食い違っている | `discrepancy_notice` | `TASK_STATE_INPUT_REQUIRED` | 同上 |
| 業務上の判断で断る | `rejection` | `TASK_STATE_REJECTED` | タスクは終わり |
| 扱えない（プロファイルが違う、版が合わない、受け付けていない種類、`message_id` の使い回し） | `error` | `TASK_STATE_REJECTED` | タスクは終わり |
| 処理の途中で想定外の失敗 | `error`（`INTERNAL_ERROR`） | `TASK_STATE_FAILED` | タスクは終わり。やり直すときは新しい `message_id` で送る |

- 終わったタスク（COMPLETED・REJECTED・FAILED・CANCELED）には、続きを送れない（A2A 3.1.1）。続きの用件は、新しいメッセージとして送る。
- `TASK_STATE_SUBMITTED` と `TASK_STATE_WORKING` は、時間のかかる処理の途中で使う。`TASK_STATE_AUTH_REQUIRED` と `TASK_STATE_CANCELED` は A2A の決まりに従い、このプロファイルでは何も足さない。

## 6. 版が合わないときの扱い

版は3か所にある。受け手は、上の行から順に確かめる。

| 何の版か | どこに書くか | 合わないときの受け手の動き | 根拠 |
|---|---|---|---|
| A2A の通信方式の版（1.0） | 要求の `A2A-Version` ヘッダ（Major.Minor） | A2A の決まりどおり、VersionNotSupportedError を返す。封筒は読まない | A2A 3.6、6.4、14.2.1 |
| プロファイルの版（A2A の拡張として） | AgentCard の拡張の URI（末尾が `/v0.1`）と `A2A-Extensions` ヘッダ | A2A の決まりに従う。必須の拡張として宣言している受け手は、その URI を名乗らない要求に ExtensionSupportRequiredError を返す。古い版へ勝手に切り替えない | A2A 3.3.4、4.6.1、4.6.3 |
| プロファイルの名前と版（封筒） | `profile`、`profile_version` | 処理をせず、`error`（`PROFILE_UNKNOWN` か `PROFILE_VERSION_UNSUPPORTED`）を返す。状態は `TASK_STATE_REJECTED` | このプロファイル |
| 共通データ契約の版 | 中身の `shipment.contract_version` | `error`（`VALIDATION_FAILED`。`issues` に `VERSION_UNSUPPORTED`）を返す。状態は `TASK_STATE_INPUT_REQUIRED` | このプロファイル |

版の決まり：

- 受け手は、自分が扱える版の一覧を持ち、一覧にない版は断る。プロファイルの版（`profile_version`）について、v0.1.0 の受け手が扱えるのは `0.1.0` だけである。
- 意味が変わる変更は2桁目を上げ（0.1 → 0.2）、拡張の URI も新しくする（A2A 4.6.3 は、互換性のない変更には新しい URI を求めている）。項目の追加だけなら3桁目を上げ、URI は変えない。
- A2A の版は Major.Minor で示し、パッチ番号は互換性に影響しない（A2A 3.6）。

共通データ契約の版は、プロファイルの版とは別に進む。

- 契約には 0.1.0 と、項目を6つ足した 0.1.1 がある（足した項目は、通知先、インボイスの金額に含まれる運賃と保険料の額、船名・航海番号・ブッキング番号。読み方は `dist/contract-v0.1/README.ja.md`）。どちらの形で調べるかは、`shipment` の中の `contract_version` で決まる。
- このプロファイル（0.1.0）の受け手は、契約 0.1.0 の `shipment` を必ず扱える。契約 0.1.1 を扱えるかどうかは、受け手による。扱えない版の `shipment` には、上の表のとおり `VERSION_UNSUPPORTED` を返す。見本の実装は、0.1.0 と 0.1.1 の両方を扱える。
- 送り手は、相手が契約 0.1.1 を扱えると分かっているときだけ、0.1.1 の `shipment` を送る。分からないときや、足した項目を使わないときは、0.1.0 のまま送る。
- 適合テスト（第9節）、メッセージの見本、台本デモは、契約 0.1.0 のデータを使っている。

## 7. 再送の扱い

A2A は、Send Message を冪等にしてよく、`messageId` で重複を見つけてよいとしている（3.3.1）。このプロファイルでは、それを受け手の決まりにする。

| 場面 | 受け手の動き | 返すもの |
|---|---|---|
| 初めて見る `message_id` | 検証して処理し、結果を `message_id` と一緒に控える | 結果 |
| 同じ `message_id` で、中身も同じ（再送） | 処理しない | 控えてある最初の結果。状態と封筒（返事の `message_id` も）は、必ず最初と同じにする。タスクも、最初と同じ識別子のものを返すのが望ましい |
| 同じ `message_id` で、中身が違う | 処理しない。控えも変えない | `error`（`MESSAGE_ID_REUSED`）。状態は `TASK_STATE_REJECTED` |
| `message_id` が UUID の形でない | 控えられないので、そのつど検証のエラーを返す | `error`（`VALIDATION_FAILED`）。状態は `TASK_STATE_INPUT_REQUIRED` |

受け手の決まり：

- 再送かどうかは、`message_id` と中身だけで見分ける。「中身が同じ」とは、JSON の値として同じことをいう。項目の並び順や、数の書き方（18 と 18.0）の違いは、違いに数えない。
- A2A では、タスクを探す前に再送を見分ける。入力待ちのタスクの続きとして送ったメッセージ（`taskId` つき）の再送にも、そのタスクが終わったあとであっても、最初と同じ返事を返す。先にタスクを探すと、終わったタスクへの続きとして A2A のエラー（3.1.1）になってしまい、送り手は結果を受け取れない。
- 同じメッセージがほぼ同時に2つ届いても、処理は1回だけにする。あとから処理に入った方には、控えてある封筒を返す。この場合に限り、タスクの識別子は最初と違ってよい。
- 控えには、失敗（`TASK_STATE_FAILED`）の結果も含める。

送り手の決まり：

- 新しいメッセージには、必ず新しい `message_id` を振る。直して送り直すときも、新しい `message_id` にする。
- 返事が届かないときは、同じ封筒を、最初と同じ送り方（新しいタスクとして、または同じタスクの続きとして）で送り直してよい。受け手は処理をやり直さない。
- 失敗のあとにやり直すときは、新しい `message_id` で送る。

## 8. 検証

`scripts/validate.py` は、ファイルの中身を見て、shipment.json かメッセージかを見分けて検証する。エラーは「コードと場所」の組で表す（一覧は `dist/contract-v0.1/README.ja.md`）。メッセージで加わるコードは次の3つである。

| コード | 意味 |
|---|---|
| `PROFILE_UNKNOWN` | `profile` がこのプロファイルの名前でない |
| `PROFILE_VERSION_UNSUPPORTED` | `profile_version` が、扱える版の一覧にない |
| `IN_REPLY_TO_REQUIRED` | 返事の型なのに、`in_reply_to` がない |

中の `shipment` で見つかった問題は、場所の先頭に `payload.shipment.` を付けて示す（例 `payload.shipment.totals.amount`）。

見本：`samples/messages/` に、10種類の型を1件ずつ置いてある。台本デモ（`scripts/demo.py`）のやり取りから取ったもので、すべて架空である。

## 9. 適合テスト

ある実装が、このプロファイルの決まりどおりに答えるかを、外から確かめる道具である。相手とは A2A（JSON-RPC）で通信するだけなので、相手の中の作りや、使っている言語は問わない。

### 9.1 実行のしかた

試す相手のエージェントを起動しておき、その URL を渡す。

```powershell
uv run python scripts\conformance.py --target http://127.0.0.1:8027
```

| 指定 | 意味 |
|---|---|
| `--target URL` | 試す相手。`URL/.well-known/agent-card.json` から AgentCard を読む |
| `--self-test` | 相手を指定する代わりに、この見本の実装を自動で起動して試す |
| `--lang ja` / `--lang en` | 表示の言語（指定しなければ両方） |
| `--json` | 結果を JSON で出す（ほかの道具から読むとき用） |
| `--quiet` | 不合格のテストと、まとめだけを出す |
| `--accepts 型,型` | 相手が引き受ける型を、AgentCard の代わりに指定する |

終了コード：0＝対象のテストがすべて合格、1＝不合格がある（対象が1件もないときも 1）、2＝相手の AgentCard を取得できない。

見本の相手側を自分で起動しておくには、別の PowerShell の窓で `uv run python scripts\serve_agent.py` を実行する（このパソコンの中だけ、127.0.0.1:8027 で待ち受ける。止めるときは Ctrl+C）。

### 9.2 テストの一覧

テストは `conformance/cases/` の JSON ファイルで、1ファイルが1件である。送るもの（入力）と、期待する答え（期待出力）の組が、手順の順に並んでいる。データはすべて架空で、ファイルは `scripts/make_samples.py` が作る（手で書かない）。

| 番号 | 確かめること | 対象になる条件 | 根拠（この文書の節） |
|---|---|---|---|
| C01 | AgentCard が、プロファイルを拡張として宣言している | いつも | 4.1 |
| C02 | 見積依頼に、見積を結果（Artifact）で返す | `quote_request` を引き受ける | 3、4、5 |
| C03 | 見積のあとのブッキング依頼に、ブッキング確認を返す | `quote_request`・`booking_request` を引き受ける | 3、5 |
| C04 | 書類の食い違いを知らせて入力待ちにし、直した再提出に申告の下書きを返す | `document_submission` を引き受ける | 3、5 |
| C05 | 申告の下書きへの承認を受け付け、封筒なしで完了にする | `document_submission`・`approval` を引き受ける | 5 |
| C06 | 見積への辞退を受け付け、封筒なしで完了にする | `quote_request`・`rejection` を引き受ける | 5 |
| C07 | 再送には、処理をやり直さず、最初と同じ封筒を返す | `quote_request` を引き受ける | 7 |
| C08 | 同じ `message_id` で中身の違うメッセージは、処理せずに断る | `quote_request` を引き受ける | 7 |
| C09 | 扱えないプロファイルの版は、処理せずに断る | いつも | 6 |
| C10 | ほかのプロファイルのメッセージは、処理せずに断る | いつも | 6 |
| C11 | 中身の項目が欠けていれば、箇所を示して入力待ちにする | `quote_request` を引き受ける | 5、8 |
| C12 | 中の `shipment` が共通データ契約に合わなければ、箇所を示して入力待ちにする | `quote_request` を引き受ける | 5、8 |
| C13 | 封筒でないメッセージ（文字だけ）は処理せず、入力待ちにするか、A2A のエラーで断る | いつも | 4.2 |
| C14 | 受け付けていない種類のメッセージは、処理せずに断る | `quote` を引き受けない | 4.1、5 |
| C15 | 誤りを直したメッセージを、同じタスクの続きとして受け付ける | `quote_request` を引き受ける | 5 |
| C16 | 必須の拡張を使うと名乗らない要求は、A2A のエラーで断る | 拡張を `required: true` と宣言している | 4.1 |
| C17 | 続きとして送ったメッセージの再送にも、タスクが終わったあとで、最初と同じ封筒を返す | `document_submission` を引き受ける | 7 |

- 対象になるかどうかは、相手の AgentCard の宣言（`params.accepts` と `required`）から決める。対象外のテストは、不合格に数えない。
- どのテストでも、次を確かめる：タスクの状態、返事の封筒の置き場所（Artifact か、状態に添えた Message か）、返事の封筒がこのプロファイルの検証に合格すること、`in_reply_to` と `correlation_id` が送ったメッセージと合っていること、エラーの `code` と `issues`（コードと場所の組。説明文は比べない）。

### 9.3 テストの書き方

| 手順の項目 | 意味 |
|---|---|
| `send` | 封筒を送る |
| `resend` | 前の手順（番号で指定）で送った封筒を、そのままもう一度送る |
| `text` | 封筒の代わりに、文字だけのメッセージを送る |
| `card` | 何も送らず、AgentCard の宣言を確かめる |
| `continue` | 前の手順（番号で指定）のタスクの続きとして送る |
| `without_extension` | プロファイルを使うと名乗らずに送る（`A2A-Extensions` ヘッダなし） |
| `expect` | 期待する答え。`state`（タスクの状態）と `reply`（返事の封筒。なければ null）、または `error`（A2A のエラーの呼び名）。答え方が2通り認められている手順では `any_of` に並べ、どれか1つに合えば合格 |

入力の中の `$id:名前` は、実行のときに新しい UUID に置き換える（同じテストの中の同じ名前は同じ値）。`$now` はいまの日時に、`$reply:手順:道筋` は前の手順で返ってきた封筒の値に置き換える。

### 9.4 適合テストが確かめないこと

- 見積の金額や日程など、業務の中身が正しいかどうか。
- 認証と、通信の暗号化。
- JSON-RPC 以外のつなぎ方（HTTP+JSON、gRPC）、ストリーミング、プッシュ通知、時間のかかる処理の途中経過。
- ほぼ同時に届いた再送の扱い（見本の実装では、別のテストで確かめている）。
- テストは、相手がすぐに答えること（見積を返す、ブッキングを確定する）を前提にしている。人の判断を挟む実装で試すには、自動で答えるテスト用の設定が要る。

## 10. MCP の道具

A2A がエージェント同士のやり取りを運ぶのに対し、MCP は、AI が使う道具を出すための決まりである。このプロファイルでは、送る前や受け取ったあとの確認に使う道具を3つ、MCP サーバーとして出す。道具は規則だけで動き、AI は使わない。渡されたデータを確かめて写すだけで、ファイルを読んだり、外部に送ったりはしない。

| 道具 | 渡すもの | 返すもの |
|---|---|---|
| `validate` | `document`（shipment.json か、メッセージの封筒） | `kind`（`shipment` か `message`）、`valid`、`errors`（コード・場所・なぜ違うか・どう直すか。日本語と英語） |
| `list_discrepancies` | `shipment` | `ok`、`count`、`discrepancies`（書類の値と正本の値の組）、`recorded_in_events`（食い違いが記録に書いてあるか）、`errors` |
| `draft_declaration` | `shipment`、`draft_number`（省略可） | `ok`、`reason`（作れなかった理由。`invalid_shipment` か `discrepancies`）、`draft`（申告の下書き（模擬））、`errors`、`discrepancies` |

- どの返事にも、2つの注意書き（`notice`。実験的な参照仕様であること、判断するのは利用者であること）が日本語と英語で入る。
- `list_discrepancies` と `draft_declaration` は、`shipment` が共通データ契約に合わないときは比べずに、`ok: false` と問題の一覧を返す（食い違いの記載漏れだけは問題に数えない）。
- `draft_declaration` は、書類の値が正本と食い違っている間は下書きを作らず、食い違いの一覧を返す。下書きは模擬で、実際の申告ではない。出典で確かめていない値は `unverified` に並ぶ。
- 起動の命令は `uv run python -m trade_agent_profile.mcp_server`（標準入出力でつなぐ）。Claude Code では、このフォルダの `.mcp.json` に登録してあり、フォルダを開くと使える（最初に、使ってよいかの確認が出る）。
- MCP の版：公式の Python 用の部品（mcp 2.3.0）を使い、現行版（2026-07-28）と、ひとつ前の版（2025-11-25）の両方のつなぎ方で道具を呼べることを、テストで確かめている。

## 11. 既知の制限と、これから決めること

- 識別 URI の住所には仕様の案内のページを、スキーマの `$id` の住所には2つのスキーマを置いてある（2026-11-23 から）。仕様の本文は、公開リポジトリの文書が正本である。
- 認証は定めていない（A2A の決まりに従う）。見本の実装は認証をせず、このパソコンの中（127.0.0.1）だけで待ち受ける。外から届く場所で動かしてはいけない。
- つなぎ方は JSON-RPC だけを試している。ストリーミングとプッシュ通知は使っていない。
- 見本の実装は、タスクとメッセージの控えを、動いている間だけ覚えている（止めると消える）。メッセージの控えは、ファイル（SQLite）に置くこともできる。
- A2A 1.0.1（2026-05-26）は不具合の直しだけの版で、公式の変更点は3件である。①仕様の例の中の状態の書き方を `TASK_STATE_*` にそろえた（状態の値そのものは変わらない）。②HTTP+JSON のつなぎ方で `application/a2a+json` を勧めるようにした（JSON-RPC は `application/json` のまま）。③gRPC と HTTP のエラーの対応表を直し、JSON-RPC のエラーの `data` を決まった形にする決まりを取り消した（最終的な文言は未確認）。見本の実装は JSON-RPC でつなぎ、エラーは種類（コード -32008 など）で見分けるので、このプロファイルを変える必要はない。`A2A-Version` は Major.Minor で示すので 1.0 のままである（3.6）。2026-11-23 の時点で、公式サイトの最新の公開版の表示は 1.0.0 のままである。
- 見本の相手側は、1社がフォワーダーと通関業者を兼ねる想定である。銀行の役割は、型（`sender.role`）だけを用意していて、見本にはない。
- 見積の料金表は架空である。申告の下書きは模擬で、実際の申告には使えない。
- 通関業法では、他人の依頼によって通関書類（税関に出す申告書など）を作ることが通関業務に含まれ（第2条第1号ロ）、業として通関業務を行う（通関業を営む）には財務大臣の許可が要る（第2条第2号、第3条第1項）。税関の通達（通関業法基本通達 2－3）によれば、「業として」とは、営利の目的をもって通関業務を反復継続して行う場合、または反復継続して行う意思をもって行う場合をいう。営利の目的が直接か間接かは問わず、ほかの業務に付帯して無償で行う場合も含まれる。このプロファイルと見本の実装は、申告を代わりに行うものではない。実際の業務で使う人は、自分の使い方が許可の要る場合にあたるかを、税関か専門家に確かめること。
