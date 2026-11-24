# 共通データ契約 v0.1.1（配布物）

> **これは実験的な参照仕様です。いずれの標準化団体の公式仕様でもありません。**

1件の船積みを1つの JSON（shipment.json）で表すための取り決めです。正本は案27（エージェント間貿易プロトコル）の `schema/` にあり、このフォルダはその写しです。最上位の値は「照合済みの正しい値」、`documents[].fields` は「その書類に書いてあった値と根拠」を表します。

判断するのは利用者です。このツールは下調べと記録を担います。

いまの版は 0.1.1 です。**前の版 0.1.0 のデータは、書き換えなくても、そのまま合格します**（下の「版について」）。

## 入っているもの

| ファイル | 中身 |
|---|---|
| `shipment.schema.json` | スキーマ（JSON Schema 2020-12）。0.1.0 と 0.1.1 の両方を、この1つで調べられる |
| `samples/valid/` | 正しい例 10件（0.1.1。すべて架空） |
| `samples/invalid/` | 誤り例 10件と、期待されるエラー（`.expected.json`）（0.1.1） |
| `samples/v0.1.0/` | 前の版 0.1.0 の見本（正しい例 10件、誤り例 10件と期待されるエラー）。最初に配ったものと同じ中身 |
| `CHANGELOG.md` | 版ごとの変更点 |

## 使い方

1. このフォルダの中身を、自分のプロジェクトの `contracts/v0.1/` に写す（前に写したものがあれば、置き換える）。
2. 写したものは書き換えない。変えたい点は、自分のプロジェクトの `docs/CONTRACT_PROPOSALS.md` に提案として書き、案27のチャットに伝える。
3. 自分の作った shipment.json を、次のどちらかで検証する。
4. 0.1.1 で足した項目を使いたいときだけ、データを 0.1.1 に書き換える（下の「0.1.0 から 0.1.1 に書き換える」）。

### 検証A：規則まで調べる（おすすめ）

案27のフォルダにある検証コマンドを、どのフォルダからでも呼べます。`<案27のフォルダ>` は2か所とも実際の場所に読み替えます（例 `C:\trade-ai\p27-protocol`）。

```powershell
uv run --project <案27のフォルダ> python <案27のフォルダ>\scripts\validate.py 自分のファイル.json
```

ファイルのほか、フォルダ、複数のファイル、ワイルドカード（`*`）も渡せます。`--lang ja` で日本語だけ、`--json` でほかのプログラムが読める形になります。0.1.0 のデータと 0.1.1 のデータが混ざっていても、1件ずつ、書いてある版に合わせて調べます。

### 検証B：スキーマだけで調べる

Python の jsonschema で、形・型・形式だけを調べられます。検査数字や合計などの規則は調べられません。スキーマが、データに書いてある `contract_version` を見て形を選ぶので、版ごとに呼び分ける必要はありません。

```python
import json
from jsonschema import Draft202012Validator

schema = json.load(open("contracts/v0.1/shipment.schema.json", encoding="utf-8"))
data = json.load(open("shipment.json", encoding="utf-8"))
for error in Draft202012Validator(schema).iter_errors(data):
    print(list(error.absolute_path), error.message)
```

## 版について

- **検証は、データに書いてある `contract_version` に合わせて形を選びます。** 0.1.0 と書いたデータは 0.1.0 の形で、0.1.1 と書いたデータは 0.1.1 の形で調べます。0.1.0 のデータを書き換える必要はありません。
- **0.1.1 のデータでは、足した項目も省けません。** この契約では、null は「書類にない・まだ分からない」、項目そのものがないのは「その版では扱わない」を意味します。0.1.1 と書いたデータで足した項目が欠けていると、どちらなのか区別できないためです。分からなければ null（通知先は空の一覧）と書きます。
- **0.1.0 のデータに、0.1.1 の項目を書くことはできません**（その版にない項目として誤りになります）。使いたいときは、データを 0.1.1 に書き換えます。
- 受け付ける版は 0.1.0 と 0.1.1 だけです。ほかの版は「版の不一致」になり、それ以上の検査はしません。
- 0.1.0 しか知らない道具は、0.1.1 のデータを「版の不一致」として断ります。相手が 0.1.1 を扱えるか分からないときは、0.1.0 のまま渡してください。

## 0.1.1 で足した項目

| 項目 | 形 | null・空 | 意味 |
|---|---|---|---|
| `parties.notify_parties` | 当事者（`name`・`address`・`country`）の一覧 | 0件可。3件まで | 通知先（Notify Party）。いないとき・分からないときは、空の一覧 `[]` |
| `trade_terms.freight_amount` | 金額（小数2桁の文字列） | null 可 | インボイスの金額（`totals.amount`）に含まれている運賃の額。含まれていないとき・分からないときは null |
| `trade_terms.insurance_premium_amount` | 金額（小数2桁の文字列） | null 可 | インボイスの金額に含まれている保険料の額。保険をかけた額（保険金額）ではない。含まれていないとき・分からないときは null |
| `transport.vessel_name` | 文字列 | null 可 | 積み地を出る本船の名前。海上輸送でないときは null |
| `transport.voyage_number` | 文字列 | null 可 | その本船の航海番号 |
| `transport.booking_number` | 文字列 | null 可 | 運送人のブッキング番号 |

- 運賃と保険料の額の通貨は、インボイスと同じ（`trade_terms.currency`）です。CFR や CIF のインボイスから、輸出の申告に使う FOB の額を出すときに使えます（輸出の申告価格は、輸出港での本船甲板渡しの価格と定められています。関税法施行令 第59条の2 第2項）。計算と判断は、利用者が行います。
- 書類から読み取った値（`documents[].fields`）のキーに、足した項目を書けます（例 `transport.vessel_name`、`parties.notify_parties[0].name`）。運賃と保険料の額は、ほかの金額と同じく、数として比べます。
- 見本では、02・03・06・08・10 に値を入れてあります（名前や番号はすべて架空）。01 は、指示書 第13節の例を、値を変えずに 0.1.1 にしたものです。

## 0.1.0 から 0.1.1 に書き換える

書き換えは、足した項目を「まだ分からない」で足し、`contract_version` を `0.1.1` にするだけです。ほかの値は変えません。案27の道具で、機械的にできます。

```powershell
uv run --project <案27のフォルダ> python <案27のフォルダ>\scripts\upgrade.py 自分のファイル.json --out 書き出し先のフォルダ
```

- もとのファイルは変えません。書き換えた写しを、`--out` のフォルダに書き出します（同じ名前のファイルがあれば、上書きしません）。
- 自分で書き換えるときは、次のとおりに足します：`parties.notify_parties` は `[]`、`trade_terms.freight_amount` と `trade_terms.insurance_premium_amount` は null、`transport.vessel_name`・`transport.voyage_number`・`transport.booking_number` は null。
- `ext.<プロジェクト名>` の下に置いてあった値は、道具では動かしません。正式の項目へ移すかどうかは、その値を置いたプロジェクトが決めます。

## 読み方（0.1.0 と 0.1.1 に共通）

指示書 第13節に書かれていない細部を、次のように確定しました。

1. **項目は、第13節の例にあるものと、0.1.1 で足した6つだけ。** 0.1.0 のデータでは、第13節の例にあるものだけです。
2. **項目は省けない。** 分からない値は、null にできる項目に限り null と書きます（下の表）。
3. **決められていない項目はエラー。** 入れ子の中も同じです。独自の項目は `ext.<プロジェクト名>` の下に置きます。プロジェクト名は英小文字で始め、英小文字・数字・ハイフン・下線だけを使います。その中身はオブジェクトで、検証では中を問いません。
4. **書類の値と正本の食い違い。** `documents[].fields` の値が正本と違うときは、`events` に `type` が `discrepancy_noted` の記録が1件以上必要です。記録があるかどうかだけを見ます（どの項目についての記録かまでは照合しません）。正本が null の項目とは比べません。金額・数量・重量・単価は数として比べます（`"22500.0"` と `"22500.00"` は同じ）。
5. **コードは形式だけを調べる。** 国・通貨・港・単位・包装・寸法型式・インコタームズは、実在するコードかどうかを調べません。
6. **受け付ける版は 0.1.0 と 0.1.1。** ほかの版は「版の不一致」になり、それ以上の検査はしません。
7. **数の書き方。** 金額は小数ちょうど2桁（円も `.00` を付ける）、数量と重量は小数0〜3桁、単価は小数0〜6桁。どれも引用符つきの文字列で、負の数と余分な先頭の 0 は使えません。個数と明細番号は引用符なしの整数です。
8. **数のまま持つ項目の扱い。** 個数・明細番号・ページ・確からしさ・位置は、引用符なしの数です。通信の方式によっては、整数が小数つきの形（18 が 18.0）で届くことがあるので、受け取る側は 18 と 18.0 を同じ数として扱ってください。桁の多い値は、数ではなく文字列で持ちます（金額・数量・重量を文字列にしているのは、このためでもあります）。
9. **日付と日時。** 日付は `YYYY-MM-DD` で、実在する日付。日時は秒までと時差が必須です（例 `2026-12-01T09:00:00+09:00`。`Z` も可）。到着予定日は出発予定日より前にできません（同じ日は可）。
10. **合計。** 明細を足した値と `totals` が一致すること。金額は必ず調べます。重量と個数は、明細と合計のどちらにも null がないときだけ調べます。
11. **コンテナ。** 番号は英大文字4文字（4文字目は U・J・Z）＋数字7桁で、ISO 6346 の検査数字を検算します。同じ番号は1回だけ。明細の `container_number` は、一覧にある番号か null です。
12. **輸出者。** `direction` が `export` のとき、`parties.exporter` は null にできません。
13. **書類から読み取った値。** `fields` のキーは、正本の1つの値への道筋です（`shipment_id`、`direction`、`status`、`parties`、`trade_terms`、`transport`、`lines`、`totals` の下）。そのデータの版にない項目は指せません。`extracted_by` が `ai` のとき `confidence` は必須。`bbox` は `[x0, top, x1, bottom]` で、x0 ≦ x1、top ≦ bottom、すべて 0 以上です。
14. **出来事。** `events[].type` は英小文字・数字・下線の名前です（例 `created`、`checked`、`discrepancy_noted`）。`by` は `human`・`rule`・`ai` のどれかです。
15. **文字コード。** UTF-8 です。先頭に BOM があっても読めますが、BOM なしを勧めます。

## 項目ごとの「必須」と「null 可」

どちらの項目も、項目そのものは省けません。「0.1.1」と付けた項目は、0.1.1 のデータにだけあります。

| まとまり | 必須（null 不可） | null 可 |
|---|---|---|
| 最上位 | `contract_version`、`shipment_id`、`direction`、`status`、`parties`、`trade_terms`、`transport`、`lines`（1件以上）、`totals`、`documents`（0件可）、`events`（0件可）、`ext`（空で可） | なし |
| `parties` | `shipper`、`consignee`、`notify_parties`（0.1.1。0〜3件の一覧） | `exporter`（輸出のときは必須） |
| 当事者1件（通知先も同じ） | `name` | `address`、`country` |
| `trade_terms` | `incoterms`、`incoterms_version`、`currency` | `place`、`payment_terms`、`freight_amount`（0.1.1）、`insurance_premium_amount`（0.1.1） |
| `transport` | `mode`、`port_of_loading`、`port_of_discharge`、`containers`（0件可） | `etd`、`eta`、`vessel_name`（0.1.1）、`voyage_number`（0.1.1）、`booking_number`（0.1.1） |
| コンテナ1件 | `number`、`seals`（0件可） | `iso_type`、`gross_weight_kg` |
| 明細1件 | `line_no`、`description`、`quantity`、`quantity_unit`、`amount` | `hs_code_jp`、`hs_code_dest`、`origin_country`、`net_weight_kg`、`gross_weight_kg`、`packages`、`package_type`、`unit_price`、`container_number` |
| `totals` | `amount` | `net_weight_kg`、`gross_weight_kg`、`packages` |
| 書類1件 | `doc_type`、`fields`（空で可） | `doc_number`、`issue_date`、`file`、`sha256` |
| 読み取った値1件 | `value`、`extracted_by` | `page`、`bbox`、`confidence`（ai のときは必須） |
| 出来事1件 | `type`、`at`、`by` | `note` |

## エラーの一覧

エラーは「コードと場所」の組で表します。場所は第13節と同じ書き方です（例 `lines[0].amount`）。説明文は変わることがあるので、プログラムで扱うときはコードと場所を使ってください。0.1.1 で、コードは増えていません。

| コード | 意味 |
|---|---|
| `FILE_UNREADABLE` / `ENCODING_INVALID` / `JSON_INVALID` | ファイルを読めない、UTF-8 でない、JSON として読めない |
| `ROOT_NOT_OBJECT` | いちばん外側がオブジェクトでない |
| `VERSION_UNSUPPORTED` | 扱えない版 |
| `REQUIRED_MISSING` / `REQUIRED_NULL` | 必須の項目がない、null にできない項目が null |
| `TYPE_MISMATCH` | 型が違う（文字列と数値の取り違えなど） |
| `ENUM_INVALID` | 決められた値のどれでもない |
| `FORMAT_INVALID` | コード・日付・数などの形式が違う、実在しない日付 |
| `UNKNOWN_FIELD` | そのデータの版にない項目（独自の項目を ext の外に置いた場合や、0.1.0 のデータに 0.1.1 の項目を書いた場合を含む） |
| `EXT_INVALID` | ext の直下の名前か中身の形が違う |
| `ARRAY_LENGTH` / `EMPTY_VALUE` / `OUT_OF_RANGE` | 要素の数（通知先が4件以上、など）、空の文字列、範囲の外 |
| `CONTAINER_CHECK_DIGIT` / `CONTAINER_DUPLICATE` | コンテナ番号の検査数字が合わない、同じ番号が重なる |
| `LINE_CONTAINER_UNKNOWN` / `LINE_NO_DUPLICATE` | 明細のコンテナが一覧にない、明細番号が重なる |
| `TOTAL_MISMATCH` | 明細の合計と totals が合わない |
| `DATE_ORDER` | 到着予定日が出発予定日より前 |
| `EXPORTER_REQUIRED` | 輸出なのに輸出者が null |
| `FIELD_PATH_INVALID` / `CONFIDENCE_REQUIRED` / `BBOX_INVALID` | fields のキーが正本を指していない、ai なのに確からしさがない、位置の並びが違う |
| `DISCREPANCY_NOT_RECORDED` | 書類の値が正本と違うのに、食い違いの記録がない |
| `SCHEMA_VIOLATION` | 上のどれにも当たらないスキーマ違反 |

検査は「版 → スキーマ（形・型・形式）→ 規則」の順に行い、前の段で問題が見つかると後ろの段は行いません。1つの原因から似たエラーがいくつも出るのを防ぐためです。`contract_version` がない、または形式が違うときは、版で形が決まる部分（`parties`・`trade_terms`・`transport`）は調べません。先に版を直すと、その部分の問題が分かります。

## 誤り例と期待結果の形

`samples/invalid/` の各ファイルには、1件につき1種類だけ誤りを入れてあります。対になる `.expected.json` は次の形です。自分の実装を試すときは、エラーのコードと場所の組が一致するかを比べます。

```json
{
  "valid": false,
  "errors": [
    { "code": "CONTAINER_CHECK_DIGIT", "path": "transport.containers[0].number" }
  ]
}
```

## 見本について

見本はすべて架空です。当事者名には Sample・Example・Demo を入れ、品名には (sample) を付けてあります。船名とブッキング番号にも、同じ語を入れてあります。品目番号は、出典で確かめていないのですべて null です。運賃と保険料の額も、形を示すための架空の数字です。形の例であり、実際の取引や規制への適合を示すものではありません。

`samples/v0.1.0/` の見本は、`samples/` の同じ名前の見本から、0.1.1 で足した項目を外しただけのものです。

## 既知の制限（v0.1.1）

- コードが実在するかどうかは調べません。
- 当事者は、荷送人・輸出者・荷受人と、通知先（3件まで）だけです。
- 運賃と保険料の額は、インボイスの金額に含まれている分だけを表します。インボイスとは別に、または別の通貨で支払った運賃や保険料（輸入で、FOB の値段に運賃を足して考える場合など）は表せません。
- 船名と航海番号は1組、ブッキング番号は1つだけです。積み替えがあって本船が2つ以上ある場合や、ブッキングが2つ以上ある場合は表せません。航空・道路・鉄道の便名も表せません。
- 荷印、住所を分けた形、当事者のコード、コンテナの風袋重量は、ありません（要るときは `ext` に置きます）。
- 食い違いの記録を、項目ごとに対応づけることはできません。
- 通貨ごとの小数の桁数の違い（円は0桁など）は扱いません。金額はどの通貨でも小数2桁で書きます。
- 揚げ地と最終の届け先が違う場合の届け先は、取引条件の指定地（`trade_terms.place`）でしか表せません。

これらは、案27の `docs/CONTRACT_PROPOSALS.md` に次の版への提案として記録してあります。
