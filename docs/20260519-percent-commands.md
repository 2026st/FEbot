# `%` プレフィックス・コマンド

## 意図

Slack スラッシュ `/fe-help` に加え、通常メッセージから `%help` などでヘルプを出せるようにする。先頭が `%` のメッセージはコマンドとして解釈し、RAG やクイズ処理に流さない。

## ルール

- トリム後の本文が `%` で始まればコマンド。
- コマンド名は `%` 直後から最初の空白まで（小文字に正規化）。
- ヘルプ別名: `help`, `febot-help`, `fe-help`（いずれも同一の `_help_text`）。
- `%` のみ: 利用法の短いヒント。
- 未知コマンド: `不明なコマンド: %foo。利用可能: %help, %febot-help`（RAG には進まない）。

## 到達経路

| 入力 | ハンドラ |
|------|----------|
| `@bot %help` | `app_mention` → `try_handle_percent_command` |
| DM `%febot-help` | `message.im` |
| ボット応答済みスレッド `%help` | `message.channels`（`bot_active`） |
| `/fe-help` | 従来どおりスラッシュ（変更なし） |

チャンネルでメンションなしの `%help` は、現状の Event 購読では届かない。

## 実装

- パース・ディスパッチ: `src/febot/slack_handlers.py`（`parse_percent_command`, `try_handle_percent_command`）
- 組み込み: `src/febot/slack_app.py` の `on_mention` / `on_message`（DM・アクティブスレッド）

## 会話履歴

ヘルプ応答は `_run_rag_if_allowed` を通さないため、スレッドの RAG 履歴には追加されない。
