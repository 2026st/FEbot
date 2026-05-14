# Bedrock `The provided model identifier is invalid`（2026-05-14）

## 症状

Slack ボットで質問すると、`febot.content_filter` や `febot.slack_app`（RAG）経由の Bedrock 呼び出しで次のようなログが出る。

- `Bedrock Converse failed (ValidationException), trying InvokeModel`
- `ValidationException: The provided model identifier is invalid`（`Converse` / `InvokeModel` の両方）

埋め込み（OpenAI）や Supabase は HTTP 200 のまま、**チャット用 Bedrock の `modelId` のみ**が失敗している状態。

## 原因（コード上の流れ）

1. [`src/febot/config.py`](../src/febot/config.py) の `Settings.load()` が `BEDROCK_CHAT_MODEL_ID`（正規化後）を解決し、空なら **既定の in-region モデル ID** を使う。
2. [`src/febot/bedrock_client.py`](../src/febot/bedrock_client.py) が `converse` / `invoke_model` の **`modelId`** にその文字列をそのまま渡す。

リージョン・アカウント・モデル提供形態によっては、**foundation model の短い ID**（例: `anthropic.claude-sonnet-4-6`）がそのリージョンのランタイムでは受け付けられず、上記の `ValidationException` になることがある。

## 対処

| 目的 | 設定例 |
|------|--------|
| まず動かす（コスト重視・東京 in-region 向け既定） | `BEDROCK_CHAT_MODEL_ID` を空のまま `USE_BEDROCK=true` にするか、明示で `anthropic.claude-3-5-haiku-20241022-v1:0` |
| 品質寄りの in-region | `anthropic.claude-3-5-sonnet-20240620-v1:0` |
| 東京で Sonnet 4.6 を **geo inference profile** で使う | AWS のモデルカードに従い `jp.anthropic.claude-sonnet-4-6` を `BEDROCK_CHAT_MODEL_ID` に指定 |

併せて確認する項目:

- **`AWS_REGION` / `AWS_DEFAULT_REGION`** が、利用するモデルが載っているリージョンと一致しているか。
- Bedrock コンソールで対象モデルの **アクセス（オンデマンド等）が有効**か。アクセス不足の場合は別メッセージ（例: `AccessDeniedException`）になりやすいが、運用で混同しないようコンソールも確認する。
- `.env` の値に **余計な引用符**が含まれていないか（実装では先頭末尾の `'` / `"` を1重だけ除去する）。

## 関連ドキュメント

- [Bedrock と OpenAI 互換の使い分け](./20260513-bedrock-openai-replacement.md)
