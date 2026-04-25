---
name: change-sync-policy
description: Keep code and docs synchronized after AI-driven edits. Use when modifying implementation, environment variables, setup commands, dependencies, or user-visible behavior to prevent drift between code, README, and .env.example across Cursor, Claude, and VSCode workflows.
---

# Change Sync Policy

このスキルは、AI が実装を変更したときに `README.md`、`.env.example`、実装、運用手順の乖離を防ぐための共通ルール。

## Intent

- 人間レビュー前提でも、最低限の整合性を機械的に維持する。
- KISS / YAGNI / DRY を守り、必要最小限の更新だけを強制する。
- エディタやAIツールに依存せず、リポジトリ内ファイルで運用を統一する。

## Scope

- 対象ツール: Cursor / Claude / VSCode（手動編集含む）
- 対象変更: 実装、環境変数、セットアップ、依存関係、仕様挙動

## Global Rules (MUST)

1. 実装を変更したら、同一タスク内で関連ドキュメントを更新する。
2. 機密情報（パスワード、APIキー、トークン）をコード・ドキュメントへ直書きしない。
3. 機密値は `.env` のみ、共有用は `.env.example` にキー名のみ記載する。
4. 非自明な変更は `docs/[YYYYMMDD]-[title].md` を追加または更新する。
5. 作業完了報告時に、更新した「実装ファイル」と「説明ファイル」を対で列挙する。

## Change Matrix (Trigger -> Required Updates)

### A. 環境変数を追加・変更・削除

- 変更例:
  - `os.getenv` / `dotenv` / `config` のキー変更
- 必須更新:
  - `.env.example`（キーの追加/削除）
  - `README.md` の環境変数セクション（用途、必須/任意、既定値、未設定時挙動）
  - `docs/[YYYYMMDD]-[title].md`（理由、影響、移行）

### B. セットアップ・起動・CLI手順を変更

- 変更例:
  - 起動コマンド、依存導入手順、前提条件変更
- 必須更新:
  - `README.md` のセットアップ/実行手順
  - `AGENT.md`（Cursor系運用メモ）
  - `CLAUDE.md`（Claude系運用メモ。存在しない場合は新規作成）
  - `docs/[YYYYMMDD]-[title].md`（変更理由、ロールバック）

### C. ユーザー向け挙動（仕様）を変更

- 変更例:
  - 応答ロジック、しきい値、フォールバック条件、入出力仕様
- 必須更新:
  - `README.md` の仕様/挙動セクション
  - `docs/[YYYYMMDD]-[title].md`（旧仕様との差分、互換性、検証結果）

### D. 依存関係を変更

- 変更例:
  - `pyproject.toml` / `requirements.txt` の更新
- 必須更新:
  - 依存ファイル本体
  - `README.md` の導入/更新手順
  - `docs/[YYYYMMDD]-[title].md`（導入理由、リスク、戻し方）

## File Writing Rules (MUST)

### `README.md`

- 「何が変わったか」「どう使うか」「互換性影響」を必ず書く。
- 環境変数は「キー名 / 必須性 / 既定値 / 未設定時挙動」を揃える。

### `.env.example`

- キー名のみを管理する（機密値禁止）。
- 実装に存在しないキーを残さない。
- 必要時のみ安全なサンプル値を使う（例: `AI_TIMEOUT_SECONDS=30`）。

### `docs/[YYYYMMDD]-[title].md`

- 最低限以下を記載:
  - Intent（なぜ変更したか）
  - Change（何を変えたか）
  - Impact（何に影響するか）
  - Verify（どう検証したか）
  - Rollback（どう戻すか）

### `AGENT.md` / `CLAUDE.md`

- 実行コマンドや運用ルールが変わったときのみ更新する。
- 内容はツール固有説明ではなく、リポジトリ運用ルールを優先する。

## Definition of Done (DoD)

以下を全て満たすまで完了扱いにしない:

1. 実装差分と説明差分が同期している。
2. `.env.example` と実装のキーが一致している。
3. 非自明な変更が `docs/[YYYYMMDD]-[title].md` に記録されている。
4. Git管理対象に機密情報が含まれていない。
5. コミット前チェックを通過している。

## Commit Gate (Self Check)

- `git diff` に意図しない差分がない。
- `README.md` / `.env.example` / 実装が矛盾していない。
- デバッグコードやコメントアウト残骸がない。
- 追加した環境変数が `README.md` と `.env.example` の両方に反映済み。

## Shared Team Enforcement (Cross-tool)

このポリシーは以下で共有する:

- `README.md`: 利用者向けの正規手順
- `AGENT.md`: Cursor系作業者向け
- `CLAUDE.md`: Claude系作業者向け
- `.github/pull_request_template.md`: エディタ非依存の最終ゲート

上記4箇所のうち、変更内容に関係する箇所は必ず同一PRで更新する。

## Example

`AI_TIMEOUT_SECONDS` を追加した場合:

1. 実装（例: `src/febot/config.py`）にキーを追加
2. `.env.example` に `AI_TIMEOUT_SECONDS=30` を追加
3. `README.md` に用途、既定値、未設定時挙動を追記
4. `docs/[YYYYMMDD]-[title].md` に理由・影響・検証を記録
5. 必要なら `AGENT.md` / `CLAUDE.md` の運用コマンドを更新
