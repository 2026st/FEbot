# Bedrock `jp.*` モデルと AWS Marketplace / IAM

## 症状

`BEDROCK_CHAT_MODEL_ID=jp.anthropic.claude-sonnet-4-6` のように **リージョン推論プロファイル（`jp.` プレフィックス）** を指定したとき、Bedrock Runtime の `Converse` または `InvokeModel` が次のように失敗することがある。

- `AccessDeniedException`
- メッセージに `aws-marketplace:ViewSubscriptions` / `Subscribe` / `AWS Marketplace` が含まれる

埋め込み（OpenAI 互換 API）は成功し、チャットだけ失敗する、という切り分けになりやすい。

## 原因

`jp.*` のような **geo / inference profile** 利用は、モデル提供形態の都合で **AWS Marketplace 側の購読・権限チェック** が挟まることがある。  
その場合、IAM に `bedrock:InvokeModel` だけを付けても不十分で、エラーに示されるとおり **Marketplace 向けアクション** と **コンソール上の利用有効化** が必要になる。

（逆に、リージョン内の通常モデル ID、例: `anthropic.claude-3-5-haiku-20241022-v1:0` は、Bedrock コンソールの「モデルアクセス」で許可されていれば Marketplace 文言なく動くことが多い。）

## 対処（どちらか）

### A. IAM と Marketplace で `jp.*` を使い続ける

1. IAM ロール（例: `febot-ec2-role`）に、エラーに書かれている Marketplace アクションを付与する（組織方針に従い最小権限で）。
2. AWS Marketplace / Bedrock コンソールで、対象モデル・推論プロファイルの **利用契約・購読** を完了する。
3. 変更反映後、数分待って再試行する（エラー文面の案内どおり）。

### B. Marketplace を避ける（推奨: まず動かすならこちら）

`.env` の `BEDROCK_CHAT_MODEL_ID` を **in-region のオンデマンドモデル ID** に変える。

例（東京 `ap-northeast-1` でよく使う既定）:

```bash
BEDROCK_CHAT_MODEL_ID=anthropic.claude-3-5-haiku-20241022-v1:0
```

Bedrock コンソールで当該モデルのアクセスが有効になっていること。

## 実装側の補助（本リポジトリ）

- `bedrock_client`: `Converse` が `AccessDeniedException` のとき **`InvokeModel` にフォールバック**する。  
  Marketplace 起因の拒否では **両方同じ理由で失敗しうる** が、`bedrock:Converse` のみ不足している環境では Invoke で通る場合がある。
- 任意: `BEDROCK_CHAT_SKIP_CONVERSE=true` で最初から `InvokeModel` のみ使う（ログを簡素化したいとき）。
- `slack_app` / `content_filter`: Marketplace 型の拒否を検知し、Slack では説明付きメッセージ、フィルターは **fail-open**（チャット不能で学習ボットが止まらないように）。

## 具体例

- **設定**: `AWS_REGION=ap-northeast-1`, `BEDROCK_CHAT_MODEL_ID=jp.anthropic.claude-sonnet-4-6`
- **IAM**: `bedrock:InvokeModel` のみ
- **結果**: `AccessDeniedException` + Marketplace 文言 → **A か B のどちらかが必要**

`BEDROCK_CHAT_MODEL_ID` を `anthropic.claude-3-5-haiku-20241022-v1:0` に変え、コンソールで Haiku を有効化すると、同じ IAM でもチャットが通る例が多い。
