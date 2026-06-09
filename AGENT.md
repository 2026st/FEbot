# AGENT.md (FEbot 専用)

このファイルは、このリポジトリで AI Agent が最初に読む前提の運用メモ。

## 必読ファイル（作業前）
- `README.md`（セットアップ、環境変数、実行手順）
- `.claude/skills/change-sync-Policy/SKILL.md`（変更時の同期ルールと DoD）
- `pyproject.toml`（Python バージョンと依存）
- `docs/20260520-remove-local-corpus.md`（ローカル corpus 廃止とベクトル DB の前提）
- `docs/20260513-bedrock-openai-replacement.md`（Bedrock 環境変数・移行時の注意）

## このプロジェクトの前提
- Python は `3.9+`。`pyproject.toml` の `requires-python` に従うこと。
- Slack Bot は Socket Mode 前提。
- RAG・Web 要約・コンテンツフィルターは [`src/febot/llm_backend.py`](src/febot/llm_backend.py)。**チャットが Bedrock のときも埋め込みは OpenAI 互換 API**（`AI_API_KEY`）。Bedrock 時は AWS 標準認証に加え `AI_API_KEY` が必要。
- `rag_enabled()` は Bedrock 選択時に AWS 認証が解決でき、かつ `AI_API_KEY` があるとき、または OpenAI 互換のみのときに `AI_API_KEY` があるとき True。
- ベクトル検索は Chroma（`CHROMA_PATH`）または Supabase。ローカル `data/corpus/` は廃止。

## 実行コマンド（基本）
- 依存導入: `python3 -m pip install -e .`
- 開発依存（CI 同等チェック用）: `python3 -m pip install -e ".[dev]"`
- PR 前品質ゲート: `python3 scripts/ci_local.py --fix`
- 追加依存を含める場合: `python3 -m pip install -r requirements.txt`
- Bot 起動: `python3 -m febot`

## 環境変数ポリシー
- 機密情報（`SLACK_TOKEN`, `SLACK_APP_TOKEN`, AWS 認証情報など）をコードへ直書きしない。
- 設定は `.env` で管理し、共有時は `.env.example` を更新する。
- 選んだバックエンドに必要な認証が無い場合は RAG 応答が無効になる前提で作業する。

## 編集ルール
- KISS / YAGNI / DRY を優先し、過剰実装を避ける。
- 既存仕様を壊す変更（特に Slack イベント処理と RAG 関連）は README と docs を同時更新する。
- コミットメッセージは `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:` のいずれかで開始する。

## 作業時チェックリスト
- 変更後に最低1回、対象機能をローカルで実行確認する。
- ベクトル DB の内容や次元を変えた場合は再投入の要否を PR や作業メモに明記する。
- 仕様や運用の説明が増えた場合は `docs/[YYYYMMDD]-[title].md` を追加する。
