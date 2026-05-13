# Bedrock と OpenAI 互換 API の使い分け（2026-05-13）

## 意図

東京リージョンの Amazon Bedrock（Claude + Titan）と、OpenAI 互換 API を **環境変数で切り替え**る。Bedrock 用のモデル ID が揃っていれば Bedrock、無ければ `AI_API_KEY` による OpenAI 互換を使う。

## どちらが選ばれるか

| 条件 | 使用するバックエンド |
|------|---------------------|
| `USE_BEDROCK` が `false` / `0` / `no` | OpenAI 互換（`AI_API_KEY` 必須） |
| `USE_BEDROCK` が `true` / `1` / `yes` | Bedrock（モデル ID 未指定時はコード既定で補完） |
| 上記以外で `BEDROCK_CHAT_MODEL_ID` と `BEDROCK_EMBEDDING_MODEL_ID` が**ともに**非空 | Bedrock |
| 上記以外 | OpenAI 互換（`AI_API_KEY` があれば RAG 有効） |

## 環境変数（参照）

| OpenAI 互換 | Bedrock |
|-------------|---------|
| `AI_API_KEY`（必須・Bedrock 未使用時） | AWS 標準認証 |
| `AI_BASE_URL`（任意） | `AWS_REGION` / `AWS_DEFAULT_REGION` |
| `AI_CHAT_MODEL` | `BEDROCK_CHAT_MODEL_ID` |
| `AI_EMBEDDING_MODEL` | `BEDROCK_EMBEDDING_MODEL_ID` |
| | `BEDROCK_EMBEDDING_DIMENSIONS`（Titan v2、既定 1024） |
| | `USE_BEDROCK`（任意・上表のとおり） |

## 移行手順

1. AWS 側で対象モデルの **オンデマンドアクセス**（または利用可能な購入済みスループット）を有効化する。
2. 実行主体（ローカルならプロファイル、本番ならタスク/EC2 ロール）に `bedrock:InvokeModel` および `bedrock:Converse`（Converse を使う場合）を付与する。
3. `.env` に [`.env.example`](../.env.example) に沿って `AWS_REGION`・`BEDROCK_*` を設定する。長期アクセスキーはリポジトリに含めない。
4. **Chroma の再生成**: 旧 OpenAI 埋め込み（例: 1536 次元）と Titan v2 既定（1024 次元）は互換でない。`data/chroma` の既存コレクションを前提にしない。`python3 scripts/ingest.py` を再実行する。
5. **距離しきい値**: `RAG_MAX_DISTANCE` は旧ベクトル空間向けの値のままでは不適切な場合がある。回答が常に「見つからない」・ノイズが増えるときは調整する。
6. **Supabase を使う場合**: pgvector の列次元が旧埋め込みに合わせて固定されている場合、スキーマ変更またはテーブル再作成後に `scripts/migrate_to_supabase.py` を再実行する。

## 実装メモ

- チャットは `bedrock-runtime` の **Converse** を優先し、失敗時は Anthropic Messages 形式の **InvokeModel** にフォールバックする（[`src/febot/bedrock_client.py`](../src/febot/bedrock_client.py)）。
- 埋め込みは Titan v2 の **InvokeModel** をテキストごとに呼び出す。

## ロールバック

`.env` で `BEDROCK_*` を外し `AI_API_KEY` のみにするか、`USE_BEDROCK=false` とする。
