# メッセージベーススラッシュコマンド

## 意図

Slack 純正の Slash Command 登録が使えない環境向けに、`/fe-help` などを通常メッセージとして解釈する。`%` プレフィックスコマンド（`docs/20260519-percent-commands.md`）は廃止し、スラッシュ形式に統一する。

## ルール

- トリム後の本文が `/fe-*` 形式ならコマンドとして解釈する（RAG やキーワード出題に流さない）。
- 利用可能: `/fe-help`, `/fe-quiz`, `/fe-format-test`
- `/` のみ: 利用法の短いヒント。
- 未知の `/fe-xxx`: エラーメッセージ（RAG には進まない）。
- `/` で始まらない通常文: コマンドではない（後段処理へ）。

## 到達経路

| 入力 | 条件 | ハンドラ |
|------|------|----------|
| `@bot /fe-help` | チャンネル | `app_mention` |
| `/fe-quiz 科目A` | ボット応答済みスレッド | `message.channels`（`bot_active`） |
| `/fe-quiz` | DM | `message.im` |
| `フォーマットテスト` | メンション・DM・スレッド | キーワード経路（後方互換） |

チャンネルでメンションなし・スレッド外の `/fe-help` は Event 購読の制約上届かない。

## `/tips`（無視マーカー）

ボットコマンドではなく、スレッド内で FEbot に反応させないためのプレフィックス。

- 条件: `thread_ts` があり、本文が `/tips` または `/tips …`
- 挙動: 無反応（`say` なし、RAG 履歴にも追加しない）
- 用途: 他ユーザーがスレッドで補足解説するときにボットを起動しない

## 実装

- パース・ディスパッチ: `src/febot/slack_handlers.py`（`parse_slash_command`, `try_handle_slash_command`, `is_tips_message`）
- 組み込み: `src/febot/slack_app.py` の `_try_slash_commands` → `on_mention` / `on_message`（DM・アクティブスレッド）
- `/tips` 無視: `on_message` でクイズ採点より前に `is_tips_message` を判定
- Slack 純正 `@app.command` ハンドラは削除（登録不要）

## 会話履歴

ヘルプ・フォーマットテスト・出題コマンドは `_run_rag_if_allowed` を通さないため、スレッドの RAG 履歴には追加されない（出題メッセージは従来どおり `sessions` に記録）。
