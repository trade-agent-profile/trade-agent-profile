# 貢献のしかた / Contributing

> これは実験的な参照仕様です。いずれの標準化団体の公式仕様でもありません。
> This is an experimental reference specification. It is not an official specification of any standards body.

English follows the Japanese.

## 日本語

### 提案するとき

- 不具合や提案は Issue で知らせてください。セキュリティの問題は Issue に書かず、`SECURITY.md` の方法で知らせてください。
- 共通データ契約（`schema/shipment.schema.json`）やメッセージの型（`schema/message.schema.json`）を変える提案には、理由と、影響を受ける項目を書いてください。受け付けた提案は `docs/CONTRACT_PROPOSALS.md` に集め、次の版で扱います。

### 変えるときの決まり

- 版：意味が変わる変更は2桁目（0.1 → 0.2）を、項目を足すだけなら3桁目を上げ、`dist/contract-v0.1/CHANGELOG.md` に書きます。
- 見本と適合テストは手で書かず、`scripts/make_samples.py` で作り直します（適合テストの中身は `scripts/make_conformance.py` に書きます）。スキーマや見本を変えたら、`scripts/build_dist.py` で配布物をそろえます。
- メッセージの型や台本デモを変えたら、`scripts/make_samples.py` と `scripts/demo.py` の両方を実行し直します。
- 決まりを足したら、適合テストを1件足し、その決まりを破った実装が不合格になることもテストで確かめます。
- エラーは「コードと場所」の組で表します。説明文を直しても、コードは変えません。
- 画面の文言は `src/trade_agent_profile/locales/ja.json` と `en.json` に置きます。コード上の名前は英語です。
- ファイルは UTF-8（BOM なし）、改行は LF です。

### 入れてはいけないもの

- 実在の企業名、実データ、個人の情報、鍵やパスワード。見本はすべて架空にし、当事者名には Sample・Example・Demo のどれかを、品名には (sample) を入れます。
- 標準（DCSA、UN/CEFACT、WCO など）の本文の転載。対応づけには、項目名と出典の URL だけを書きます。

### 確かめ方

次の2行を1行ずつ実行します。Ruff、テスト、見本の検証、公開前の検査（1段目）、適合テストがまとめて走り、最後の行に `CHECK OK` と出れば合格です。

```powershell
uv sync
```

```powershell
uv run python scripts\check.py
```

### ライセンス

送っていただいた変更は、コード・スキーマ・見本・適合テストは Apache License 2.0（`LICENSE`）、文書は CC BY 4.0（`LICENSE-DOCS.md`）で提供されることに同意したものとして扱います。

## English

### Proposing changes

- Report bugs and ideas as issues. Do not report security problems in public issues; follow `SECURITY.md` instead.
- A proposal to change the shared data contract (`schema/shipment.schema.json`) or the message types (`schema/message.schema.json`) should state the reason and the affected fields. Accepted proposals are collected in `docs/CONTRACT_PROPOSALS.md` and handled in the next version.

### Rules for changes

- Versioning: a change of meaning raises the second digit (0.1 → 0.2); only adding fields raises the third digit. Record it in `dist/contract-v0.1/CHANGELOG.md`.
- Do not edit samples or conformance cases by hand. Regenerate them with `scripts/make_samples.py` (conformance cases are defined in `scripts/make_conformance.py`). After changing schemas or samples, run `scripts/build_dist.py`.
- After changing message types or the scripted demo, run both `scripts/make_samples.py` and `scripts/demo.py`.
- When you add a rule, add a conformance case, and a test showing that an implementation breaking the rule fails.
- Errors are identified by a code and a location. Rewording an explanation never changes the code.
- User-facing text lives in `src/trade_agent_profile/locales/ja.json` and `en.json`. Names in code are in English.
- Files are UTF-8 without BOM, with LF line endings.

### What must not be added

- Real company names, real data, personal information, keys or passwords. All samples are fictitious: party names contain Sample, Example or Demo, and descriptions contain (sample).
- Copies of the text of standards (DCSA, UN/CEFACT, WCO, and so on). Mappings list only field names and source URLs.

### How to check

Run the two commands above, one at a time. They run Ruff, the tests, sample validation, the pre-publication check (stage 1) and the conformance tests. The last line must be `CHECK OK`.

### License

By contributing, you agree that your code, schemas, samples and conformance cases are provided under the Apache License 2.0 (`LICENSE`), and your documentation under CC BY 4.0 (`LICENSE-DOCS.md`).
