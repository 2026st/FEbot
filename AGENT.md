# AGENT.md (FEbot 専用)

このファイルは、このリポジトリで AI Agent が最初に読む前提の運用メモ。

## 必読ファイル（作業前）
- `README.md`（セットアップ、環境変数、実行手順）
- `pyproject.toml`（Python バージョンと依存）
- `docs/20260405-ipa-corpus.md`（IPA コーパス再生成の前提）
- `docs/20260416-bedrock-migration.md`（Bedrock 関連の現状メモ）

## このプロジェクトの前提
- Python は `3.9+`。`pyproject.toml` の `requires-python` に従うこと。
- Slack Bot は Socket Mode 前提。
- 現行の RAG パイプラインは OpenAI 互換 API 前提（`config.py` / `rag.py` / `scripts/ingest.py`）。
- `src/febot/llm.py` は存在するが、現行応答パイプラインには未接続。

## 実行コマンド（基本）
- 依存導入: `python3 -m pip install -e .`
- 追加依存を含める場合: `python3 -m pip install -r requirements.txt`
- コーパス埋め込み: `python3 scripts/ingest.py`
- Bot 起動: `python3 -m febot`
- IPA コーパス再取得: `python3 scripts/ipa_build_corpus.py --fetch`

## 環境変数ポリシー
- 機密情報（`SLACK_TOKEN`, `SLACK_APP_TOKEN`, `AI_API_KEY` など）をコードへ直書きしない。
- 設定は `.env` で管理し、共有時は `.env.example` を更新する。
- `AI_API_KEY` 未設定時は RAG 応答と ingest が無効になる前提で作業する。

## 編集ルール
- KISS / YAGNI / DRY を優先し、過剰実装を避ける。
- 既存仕様を壊す変更（特に Slack イベント処理と RAG 関連）は README と docs を同時更新する。
- コミットメッセージは `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:` のいずれかで開始する。

## 作業時チェックリスト
- 変更後に最低1回、対象機能をローカルで実行確認する。
- RAG に関わる変更では `scripts/ingest.py` の再実行要否を明記する。
- 仕様や運用の説明が増えた場合は `docs/[YYYYMMDD]-[title].md` を追加する。
