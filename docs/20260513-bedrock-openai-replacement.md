# Bedrock と OpenAI 互換 API の使い分け（2026-05-13）

`ValidationException: The provided model identifier is invalid` のときは [Bedrock チャット用モデル ID のトラブルシュート](./20260514-bedrock-chat-model-invalid.md) を参照。`AccessDeniedException` で `aws-marketplace:ViewSubscriptions` / `Subscribe` が出る場合は [Marketplace IAM と geo profile](./20260514-bedrock-marketplace-access.md) を参照。

## 意図

チャットは **Amazon Bedrock** または **OpenAI 互換 API** を環境で切り替える。**埋め込み（ingest・RAG のクエリベクトル）は常に OpenAI 互換 API**（`openai` クライアント、`AI_API_KEY`）を使う。Bedrock でチャットする構成でも Titan 等の Bedrock 埋め込みは使わない。

## どちらが選ばれるか

| 条件 | チャット | 埋め込み |
|------|----------|----------|
| `USE_BEDROCK` が `false` / `0` / `no` | OpenAI 互換 | OpenAI 互換 |
| `USE_BEDROCK` が `true` / `1` / `yes` | Bedrock | OpenAI 互換 |
| 上記以外で `BEDROCK_CHAT_MODEL_ID` が非空 | Bedrock | OpenAI 互換 |
| 上記以外 | OpenAI 互換 | OpenAI 互換 |

`rag_enabled()` が True になるには、**常に `AI_API_KEY` が必要**。Bedrock 利用時はさらに AWS 認証が解決でき、`BEDROCK_CHAT_MODEL_ID`（または `USE_BEDROCK=true` 時の既定 `anthropic.claude-3-5-haiku-20241022-v1:0`）が揃っていること。

## 環境変数（参照）

| 用途 | 変数 |
|------|------|
| 埋め込み（必ず OpenAI 互換経由） | `AI_API_KEY`、`AI_EMBEDDING_MODEL`、任意 `AI_BASE_URL` |
| OpenAI 互換のみのチャット | 上記に加え `AI_CHAT_MODEL` |
| Bedrock のチャット | AWS 標準認証、`AWS_REGION` / `AWS_DEFAULT_REGION`、`BEDROCK_CHAT_MODEL_ID`、`USE_BEDROCK`（任意） |

`BEDROCK_EMBEDDING_MODEL_ID` / `BEDROCK_EMBEDDING_DIMENSIONS` は **ランタイムの埋め込みには使わない**（互換のため設定に残せるが、[`BedrockClient`](../src/febot/bedrock_client.py) の Titan 用コードはハイブリッド経路では呼ばれない）。

## 移行手順

1. AWS 側でチャットモデルの **オンデマンドアクセス**（または利用可能な購入済みスループット）を有効化する。
2. 実行主体に `bedrock:InvokeModel` および `bedrock:Converse`（利用する場合）を付与する。`jp.anthropic.*` など **geo inference profile** を使う場合は、追加で [Marketplace 向け IAM](./20260514-bedrock-marketplace-access.md) が必要になることがある。
3. `.env` に [`.env.example`](../.env.example) に沿って AWS と `BEDROCK_CHAT_MODEL_ID` を設定し、**埋め込み用に `AI_API_KEY`** を設定する。
4. **Chroma の再生成**: 旧 Titan（1024 次元）などと `AI_EMBEDDING_MODEL` の次元が異なる場合は `python3 scripts/ingest.py` を再実行する。
5. **距離しきい値**: `RAG_MAX_DISTANCE` はベクトル空間に依存する。回答品質が変わったら調整する。
6. **Supabase**: pgvector の列次元は `AI_EMBEDDING_MODEL` に合わせる。

## 実装メモ

- チャットは `bedrock-runtime` の **Converse** を優先し、失敗時は Anthropic Messages 形式の **InvokeModel** にフォールバックする（[`src/febot/bedrock_client.py`](../src/febot/bedrock_client.py)）。
- 埋め込みは [`src/febot/llm_backend.py`](../src/febot/llm_backend.py) の `BedrockChatOpenAIEmbedBackend` が **OpenAI 互換の Embeddings API** を呼ぶ。

## ロールバック

`.env` で `BEDROCK_CHAT_MODEL_ID` を外し `USE_BEDROCK=false` とするか、チャットも `AI_API_KEY` のみに戻す。
