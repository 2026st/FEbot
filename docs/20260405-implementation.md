# 実装メモ（2026-04-05）

## 概要

[提案書.md](../提案書.md) の MVP に沿い、Socket Mode の Slack ボットと RAG（Chroma + OpenAI 互換 API）を実装した。

## 構成

| パス | 役割 |
|------|------|
| `src/febot/config.py` | `SLACK_TOKEN`, `SLACK_APP_TOKEN`, `AI_API_KEY`, `AI_BASE_URL` 等 |
| `src/febot/rag.py` | ベクトル検索、チャット生成、ユーザー単位の簡易レート制限 |
| `src/febot/quiz.py` | 練習問題 Markdown の `id:` ブロック解析（データ未設定時は空） |
| `src/febot/slack_app.py` | Bolt ハンドラ、`/fe-help`、メンション・DM・スレッド解答 |
| `src/febot/web_search.py` | DuckDuckGo 検索と Web 要約 |

ローカル `data/corpus/` と `scripts/ingest.py` は 2026-05-20 に廃止。詳細は [20260520-remove-local-corpus.md](20260520-remove-local-corpus.md)。

## 運用上の注意

- RAG 利用時は `CHROMA_PATH` に `febot_corpus` コレクション、または Supabase にベクトルデータが必要。
- スレッド単位の会話履歴・練習問題状態は **インメモリ** の `ThreadSessionStore`（`thread_session.py`）で保持する（プロセス再起動で失われる）。詳細は [20260519-thread-conversation-history.md](20260519-thread-conversation-history.md)。
- 本番ではログ方針・コスト上限・Redis 等の状態保持を別途設計すること。

## 具体例

- チャンネルで `@FEbot TCP と UDP の違いは？` → ベクトル DB を参照して回答。未ヒット時は Web 検索。
- `過去問` とメンション → 練習問題データが無い場合は「練習問題データが見つかりません。」
