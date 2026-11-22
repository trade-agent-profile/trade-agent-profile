# 共通データ契約 v0.1.0（配布物）

> **これは実験的な参照仕様です。いずれの標準化団体の公式仕様でもありません。**

1件の船積みを1つの JSON（shipment.json）で表すための取り決めです。正本は案27（エージェント間貿易プロトコル）の `schema/` にあり、このフォルダはその写しです。最上位の値は「照合済みの正しい値」、`documents[].fields` は「その書類に書いてあった値と根拠」を表します。

判断するのは利用者です。このツールは下調べと記録を担います。

## 入っているもの

| ファイル | 中身 |
|---|---|
| `shipment.schema.json` | スキーマ（JSON Schema 2020-12） |
| `samples/valid/` | 正しい例 10件（すべて架空） |
| `samples/invalid/` | 誤り例 10件と、期待されるエラー（`.expected.json`） |
| `CHANGELOG.md` | 版ごとの変更点 |

## 使い方

1. このフォルダの中身を、自分のプロジェクトの `contracts/v0.1/` に写す。
2. 写したものは書き換えない。変えたい点は、自分のプロジェクトの `docs/CONTRACT_PROPOSALS.md` に提案として書き、案27のチャットに伝える。
3. 自分の作った shipment.json を、次のどちらかで検証する。

### 検証A：規則まで調べる（おすすめ）

案27のフォルダにある検証コマンドを、どのフォルダからでも呼べます。`<案27のフォルダ>` は2か所とも実際の場所に読み替えます（例 `C:\trade-ai\p27-protocol`）。

```powershell
uv run --project <案27のフォルダ> python <案27のフォルダ>\scripts\validate.py 自分のファイル.json
```

ファイルのほか、フォルダ、複数のファイル、ワイルドカード（`*`）も渡せます。`--lang ja` で日本語だけ、`--json` でほかのプログラムが読める形になります。

### 検証B：スキーマだけで調べる

Python の jsonschema で、形・型・形式だけを調べられます。検査数字や合計などの規則は調べられません。

```python
import json
from jsonschema import Draft202012Validator

schema = json.load(open("contracts/v0.1/shipment.schema.json", encoding="utf-8"))
data = json.load(open("shipment.json", encoding="utf-8"))
for error in Draft202012Validator(schema).iter_errors(data):
    print(list(error.absolute_path), error.message)
```

## v0.1.0 の読み方

指示書 第13節に書かれていない細部を、次のように確定しました。

1. **項目は第13節の例にあるものだけ。** 足しも引きもしていません。
2. **項目は省けない。** 分からない値は、null にできる項目に限り null と書きます（下の表）。
3. **例にない項目はエラー。** 入れ子の中も同じです。独自の項目は `ext.<プロジェクト名>` の下に置きます。プロジェクト名は英小文字で始め、英小文字・数字・ハイフン・下線だけを使います。その中身はオブジェクトで、検証では中を問いません。
4. **書類の値と正本の食い違い。** `documents[].fields` の値が正本と違うときは、`events` に `type` が `discrepancy_noted` の記録が1件以上必要です。v0.1.0 は記録があるかどうかだけを見ます（どの項目についての記録かまでは照合しません）。正本が null の項目とは比べません。金額・数量・重量・単価は数として比べます（`"22500.0"` と `"22500.00"` は同じ）。
5. **コードは形式だけを調べる。** 国・通貨・港・単位・包装・寸法型式・インコタームズは、実在するコードかどうかを調べません。
6. **受け付ける版は 0.1.0 だけ。** ほかの版は「版の不一致」になり、それ以上の検査はしません。
7. **数の書き方。** 金額は小数ちょうど2桁（円も `.00` を付ける）、数量と重量は小数0〜3桁、単価は小数0〜6桁。どれも引用符つきの文字列で、負の数と余分な先頭の 0 は使えません。個数と明細番号は引用符なしの整数です。
8. **日付と日時。** 日付は `YYYY-MM-DD` で、実在する日付。日時は秒までと時差が必須です（例 `2026-12-01T09:00:00+09:00`。`Z` も可）。到着予定日は出発予定日より前にできません（同じ日は可）。
9. **合計。** 明細を足した値と `totals` が一致すること。金額は必ず調べます。重量と個数は、明細と合計のどちらにも null がないときだけ調べます。
10. **コンテナ。** 番号は英大文字4文字（4文字目は U・J・Z）＋数字7桁で、ISO 6346 の検査数字を検算します。同じ番号は1回だけ。明細の `container_number` は、一覧にある番号か null です。
11. **輸出者。** `direction` が `export` のとき、`parties.exporter` は null にできません。
12. **書類から読み取った値。** `fields` のキーは、正本の1つの値への道筋です（`shipment_id`、`direction`、`status`、`parties`、`trade_terms`、`transport`、`lines`、`totals` の下）。`extracted_by` が `ai` のとき `confidence` は必須。`bbox` は `[x0, top, x1, bottom]` で、x0 ≦ x1、top ≦ bottom、すべて 0 以上です。
13. **出来事。** `events[].type` は英小文字・数字・下線の名前です（例 `created`、`checked`、`discrepancy_noted`）。`by` は `human`・`rule`・`ai` のどれかです。
14. **文字コード。** UTF-8 です。先頭に BOM があっても読めますが、BOM なしを勧めます。

## 項目ごとの「必須」と「null 可」

どちらの項目も、項目そのものは省けません。

| まとまり | 必須（null 不可） | null 可 |
|---|---|---|
| 最上位 | `contract_version`、`shipment_id`、`direction`、`status`、`parties`、`trade_terms`、`transport`、`lines`（1件以上）、`totals`、`documents`（0件可）、`events`（0件可）、`ext`（空で可） | なし |
| `parties` | `shipper`、`consignee` | `exporter`（輸出のときは必須） |
| 当事者1件 | `name` | `address`、`country` |
| `trade_terms` | `incoterms`、`incoterms_version`、`currency` | `place`、`payment_terms` |
| `transport` | `mode`、`port_of_loading`、`port_of_discharge`、`containers`（0件可） | `etd`、`eta` |
| コンテナ1件 | `number`、`seals`（0件可） | `iso_type`、`gross_weight_kg` |
| 明細1件 | `line_no`、`description`、`quantity`、`quantity_unit`、`amount` | `hs_code_jp`、`hs_code_dest`、`origin_country`、`net_weight_kg`、`gross_weight_kg`、`packages`、`package_type`、`unit_price`、`container_number` |
| `totals` | `amount` | `net_weight_kg`、`gross_weight_kg`、`packages` |
| 書類1件 | `doc_type`、`fields`（空で可） | `doc_number`、`issue_date`、`file`、`sha256` |
| 読み取った値1件 | `value`、`extracted_by` | `page`、`bbox`、`confidence`（ai のときは必須） |
| 出来事1件 | `type`、`at`、`by` | `note` |

## エラーの一覧

エラーは「コードと場所」の組で表します。場所は第13節と同じ書き方です（例 `lines[0].amount`）。説明文は変わることがあるので、プログラムで扱うときはコードと場所を使ってください。

| コード | 意味 |
|---|---|
| `FILE_UNREADABLE` / `ENCODING_INVALID` / `JSON_INVALID` | ファイルを読めない、UTF-8 でない、JSON として読めない |
| `ROOT_NOT_OBJECT` | いちばん外側がオブジェクトでない |
| `VERSION_UNSUPPORTED` | 扱えない版 |
| `REQUIRED_MISSING` / `REQUIRED_NULL` | 必須の項目がない、null にできない項目が null |
| `TYPE_MISMATCH` | 型が違う（文字列と数値の取り違えなど） |
| `ENUM_INVALID` | 決められた値のどれでもない |
| `FORMAT_INVALID` | コード・日付・数などの形式が違う、実在しない日付 |
| `UNKNOWN_FIELD` | この版にない項目（独自の項目を ext の外に置いた場合を含む） |
| `EXT_INVALID` | ext の直下の名前か中身の形が違う |
| `ARRAY_LENGTH` / `EMPTY_VALUE` / `OUT_OF_RANGE` | 要素の数、空の文字列、範囲の外 |
| `CONTAINER_CHECK_DIGIT` / `CONTAINER_DUPLICATE` | コンテナ番号の検査数字が合わない、同じ番号が重なる |
| `LINE_CONTAINER_UNKNOWN` / `LINE_NO_DUPLICATE` | 明細のコンテナが一覧にない、明細番号が重なる |
| `TOTAL_MISMATCH` | 明細の合計と totals が合わない |
| `DATE_ORDER` | 到着予定日が出発予定日より前 |
| `EXPORTER_REQUIRED` | 輸出なのに輸出者が null |
| `FIELD_PATH_INVALID` / `CONFIDENCE_REQUIRED` / `BBOX_INVALID` | fields のキーが正本を指していない、ai なのに確からしさがない、位置の並びが違う |
| `DISCREPANCY_NOT_RECORDED` | 書類の値が正本と違うのに、食い違いの記録がない |
| `SCHEMA_VIOLATION` | 上のどれにも当たらないスキーマ違反 |

検査は「版 → スキーマ（形・型・形式）→ 規則」の順に行い、前の段で問題が見つかると後ろの段は行いません。1つの原因から似たエラーがいくつも出るのを防ぐためです。

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

見本はすべて架空です。当事者名には Sample・Example・Demo を入れ、品名には (sample) を付けてあります。品目番号は、出典で確かめていないのですべて null です。形の例であり、実際の取引や規制への適合を示すものではありません。

## 既知の制限（v0.1.0）

- コードが実在するかどうかは調べません。
- 当事者は荷送人・輸出者・荷受人の3つだけです（通知先などはありません）。
- 食い違いの記録を、項目ごとに対応づけることはできません。
- 通貨ごとの小数の桁数の違い（円は0桁など）は扱いません。金額はどの通貨でも小数2桁で書きます。
- 揚げ地と最終の届け先が違う場合の届け先は、取引条件の指定地（`trade_terms.place`）でしか表せません。

これらは、案27の `docs/CONTRACT_PROPOSALS.md` に次の版への提案として記録してあります。
