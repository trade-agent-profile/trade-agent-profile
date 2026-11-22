# セキュリティの問題の知らせ方 / Security policy

> これは実験的な参照仕様です。いずれの標準化団体の公式仕様でもありません。
> This is an experimental reference specification. It is not an official specification of any standards body.

English follows the Japanese.

## 日本語

### 対象

- 版 0.1.x（実験的）。直すのは最新の版だけです。
- 対象になるもの：検証のライブラリとコマンド、見本の A2A エージェント、MCP サーバー、適合テストの実行コマンド、公開前の検査の道具。
- 見本の実装は、試すためのものです。待ち受けはそのパソコンの中（127.0.0.1）だけで、本番で使うことは想定していません。

### 知らせ方

- 公開の Issue には書かないでください。
- このリポジトリの「Advisories」のページにある「Report a vulnerability」から、非公開で知らせてください（GitHub の非公開の報告機能）。
- 再現の手順と、影響の範囲を書いてください。実データや個人の情報は入れないでください。

### 知らせていただいたあと

- 内容を確かめ、直し方と公開の時期をご相談します。少人数で運営しているため、返事の期限はお約束できません。

## English

### Scope

- Version 0.1.x (experimental). Only the latest version receives fixes.
- In scope: the validation library and commands, the reference A2A agents, the MCP server, the conformance runner, and the pre-publication check.
- The reference implementation is for trying things out. It listens only on the local computer (127.0.0.1) and is not meant for production use.

### How to report

- Please do not open a public issue.
- Use "Report a vulnerability" on this repository's "Advisories" page (GitHub private vulnerability reporting).
- Include the steps to reproduce and the impact. Do not include real data or personal information.

### After you report

- We will confirm the report and discuss a fix and the disclosure timing with you. This is a small project, so we cannot promise a response time.
