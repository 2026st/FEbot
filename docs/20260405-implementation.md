# 実装メモ（2026-04-05）

## 概要

[提案書.md](../提案書.md) の MVP に沿い、Socket Mode の Slack ボットと RAG（Chroma + OpenAI 互換 API）を実装した。

## 構成

| パス | 役割 |
|------|------|
| `src/febot/config.py` | `SLACK_TOKEN`, `SLACK_APP_TOKEN`, `AI_API_KEY`, `AI_BASE_URL` 等 |
| `src/febot/rag.py` | 埋め込み検索、チャット生成、ユーザー単位の簡易レート制限 |
| `src/febot/quiz.py` | `sample-questions.md` の `id:` ブロック解析 |
| `src/febot/slack_app.py` | Bolt ハンドラ、`/fe-help`、メンション・DM・スレッド解答 |
| `scripts/ingest.py` | コーパスチャンク化と Chroma 投入（フルリフレッシュ） |
| `data/corpus/` | オリジナル教材（IPA 転載なし） |

## 運用上の注意

- 初回・コーパス更新後は必ず `python scripts/ingest.py` を実行してから `python -m febot` を起動する。
- スレッド単位の会話履歴・練習問題状態は **インメモリ** の `ThreadSessionStore`（`thread_session.py`）で保持する（プロセス再起動で失われる）。詳細は [20260519-thread-conversation-history.md](20260519-thread-conversation-history.md)。
- 本番ではログ方針・コスト上限・Redis 等の状態保持を別途設計すること。

## 具体例

- チャンネルで `@FEbot TCP と UDP の違いは？` → RAG が `glossary.md` 等を参照して回答。
- `過去問` とメンション → `sample-questions.md` からランダム出題し、同スレッドで `イ` と返信すると正誤と解説を返す。
