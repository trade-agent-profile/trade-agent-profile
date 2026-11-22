# 既存の標準との対応表（MAPPING）

> **これは実験的な参照仕様です。いずれの標準化団体の公式仕様でもありません。**

判断するのは利用者です。このツールは下調べと記録を担います。

共通データ契約 v0.1.0（`schema/shipment.schema.json`）の項目が、既存の標準のどの項目にあたるかを示す。

- 書くのは、項目名と出典（URL と確認日）だけである。標準の本文は転載しない。出典の URL と確認日は、表ごとに表の上に書く。
- 対応は、この案が項目名と型を見て判断したもので、各標準の団体が認めたものではない。使う前に、出典で意味を確かめること。
- 「近い」は、意味・単位・数え方が少し違うもの。「対応なし」は、同じ意味の項目が見当たらないもの。
- 利用条件を確かめられない標準は「条件未確認」とし、対応づけを保留する。

## 1. 標準ごとの状態

| 標準 | 調べた版 | 利用条件 | 状態 |
|---|---|---|---|
| DCSA Shipping Instructions and Transport Document API（船荷証券・海上運送状） | 3.0.3（SwaggerHub で公開されている最新） | Apache 2.0（仕様の中のライセンスの表示） | 対応づけた（第2節） |
| TradeTrust schemata（bill-of-lading 1.0、invoice 1.0） | 1.0 | Apache-2.0（リポジトリのライセンス） | 対応づけた（第3節） |
| UN/CEFACT Web Vocabulary | — | 利用条件は、個人の非商用の利用に限って写しを認めている。公開の表に用語の名前を載せてよいかは書かれていない | 条件未確認。保留 |
| ICC DSI Key Trade Documents and Data Elements（KTDDE） | — | KTDDE のページに、利用条件の表示が見当たらない | 条件未確認。保留 |
| WCO Data Model | — | 閲覧には無料の登録が要る。要素の名前を公開してよいかの条件は、公開のページに書かれていない | 条件未確認。保留 |

保留した標準の確かめ方は第5節にある。

## 2. DCSA（船荷証券・海上運送状）

出典：<https://app.swaggerhub.com/apis/dcsaorg/DCSA_EBL/3.0.3>（スキーマ `TransportDocument`。確認日 2026-11-23）

当事者の役割名（`shipper`、`consignee`）は、契約を作るときに DCSA に合わせてある。

| この契約の項目 | DCSA の項目 |
|---|---|
| `parties.shipper.name` | `documentParties.shipper.partyName` |
| `parties.shipper.address` | 近い：`documentParties.shipper.addressLines`（`address` に分けて書くこともできる） |
| `parties.shipper.country` | `documentParties.shipper.address.countryCode` |
| `parties.consignee.name` | `documentParties.consignee.partyName` |
| `parties.exporter` | 対応なし |
| `trade_terms`（取引条件、通貨、支払条件） | 対応なし |
| `transport.port_of_loading` | `transports.portOfLoading.UNLocationCode` |
| `transport.port_of_discharge` | `transports.portOfDischarge.UNLocationCode` |
| `transport.etd` | `transports.plannedDepartureDate` |
| `transport.eta` | `transports.plannedArrivalDate` |
| `transport.containers[].number` | `utilizedTransportEquipments[].equipment.equipmentReference` |
| `transport.containers[].iso_type` | `utilizedTransportEquipments[].equipment.ISOEquipmentCode` |
| `transport.containers[].seals[]` | `utilizedTransportEquipments[].seals[].number` |
| `transport.containers[].gross_weight_kg` | 近い：`consignmentItems[].cargoItems[].cargoGrossWeight` のうち、`equipmentReference` がそのコンテナのものの合計 |
| `lines[]`（明細1行） | 近い：`consignmentItems[]`（コンテナごとの内訳は `cargoItems[]`） |
| `lines[].description` | `consignmentItems[].descriptionOfGoods` |
| `lines[].hs_code_jp`、`lines[].hs_code_dest` | 近い：`consignmentItems[].HSCodes`、`consignmentItems[].extendedNationalCommodityCodes[]` |
| `lines[].net_weight_kg` | `consignmentItems[].cargoItems[].cargoNetWeight`（`unit` は `KGM`） |
| `lines[].gross_weight_kg` | `consignmentItems[].cargoItems[].cargoGrossWeight`（`unit` は `KGM`） |
| `lines[].packages` | `consignmentItems[].cargoItems[].outerPackaging.numberOfPackages` |
| `lines[].package_type` | `consignmentItems[].cargoItems[].outerPackaging.packageCode` |
| `lines[].container_number` | `consignmentItems[].cargoItems[].equipmentReference` |
| `lines[].quantity`、`lines[].unit_price`、`lines[].amount`、`totals` | 対応なし |
| `documents[].doc_number`（船荷証券・海上運送状） | `transportDocumentReference` |
| `documents[].issue_date`（同） | `issueDate` |

## 3. TradeTrust

出典：<https://github.com/TradeTrust/schemata>（`src/io/tradetrust/bill-of-lading/1.0/schema.json` と `src/io/tradetrust/invoice/1.0/schema.json`。確認日 2026-11-23）

### 3.1 船荷証券（bill-of-lading 1.0）

| この契約の項目 | TradeTrust の項目 |
|---|---|
| `documents[].doc_number`（船荷証券） | `blNumber` |
| `parties.shipper.name` | `shipper.name` |
| `parties.shipper.address` | 近い：`shipper.address.street` |
| `parties.shipper.country` | 近い：`shipper.address.country` |
| `parties.consignee.name` | `consignee.name` |
| `transport.port_of_loading` | 近い：`portOfLoading`（文字の項目） |
| `transport.port_of_discharge` | 近い：`portOfDischarge`（文字の項目） |
| `lines[].description` | `packages[].description` |
| `lines[].gross_weight_kg` | 近い：`packages[].weight`（文字の項目） |
| `transport.containers` | 対応なし |

### 3.2 インボイス（invoice 1.0）

| この契約の項目 | TradeTrust の項目 |
|---|---|
| `documents[].doc_number`（インボイス） | `id` |
| `documents[].issue_date`（同） | `date` |
| `parties.shipper.name` または `parties.exporter.name`（売り手） | `billFrom.name` |
| `parties.consignee.name`（買い手） | 近い：`billTo.name`、`billTo.company.name` |
| `lines[].description` | `billableItems[].description` |
| `lines[].quantity` | `billableItems[].quantity` |
| `lines[].unit_price` | `billableItems[].unitPrice` |
| `lines[].amount` | `billableItems[].amount` |
| `totals.amount` | 近い：`subtotal`（`tax`、`total` は別の項目） |
| `trade_terms.payment_terms` | 近い：`terms`（意味は未確認） |
| `trade_terms.currency` | 対応なし |

## 4. 書類の種類（`documents[].doc_type`）

| この契約の `doc_type` | DCSA | TradeTrust |
|---|---|---|
| `bill_of_lading` | `transportDocumentTypeCode` の `BOL` | bill-of-lading 1.0 |
| `sea_waybill` | `transportDocumentTypeCode` の `SWB` | 対応なし |
| `commercial_invoice` | 対応なし | invoice 1.0 |
| そのほか | 対応なし | 対応なし |

## 5. 保留した標準の確かめ方

| 標準 | 読んだページ（2026-11-23） | 確かめ方 |
|---|---|---|
| UN/CEFACT Web Vocabulary | <https://vocabulary.uncefact.org/home/terms> | UNECE（UN/CEFACT の事務局）に、公開の対応表に用語の名前と URL を載せてよいかを問い合わせる |
| ICC DSI KTDDE | <https://www.digitalizetrade.org/ktdde>、<https://www.dsi.iccwbo.org/> | ページの下にある利用条件のページ（国連 ESCAP の terms of use）を読む。それでも分からなければ ICC DSI に問い合わせる |
| WCO Data Model | <https://www.wcoomd.org/en/topics/facilitation/instrument-and-tools/tools/data-model.aspx> | 無料の登録の前に、アプリの利用条件を読み、要素の名前を公開してよいかを確かめる |
