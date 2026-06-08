# 練習問題の選択肢ボタン

## Intent

練習問題の選択肢を Slack Block Kit のボタンで選べるようにし、スレッドへの「ア」〜「エ」入力と併用できるようにする。

## Change

| ファイル | 内容 |
|---------|------|
| `src/febot/quiz.py` | `parse_choice_lines` で選択肢行をパース |
| `src/febot/slack_handlers.py` | `build_quiz_message`（選択肢ごとに section + button）、`handle_quiz_button` |
| `src/febot/slack_app.py` | 出題を Block Kit 化、`@app.action("quiz_answer")` を追加 |
| `tests/test_quiz_blocks.py` | パース・ブロック・ボタン採点のテスト |

各選択肢は `section` 内に本文を表示し、`accessory` のボタン（ア/イ/ウ/エ）で解答する。

## Impact

- Slack アプリに **Interactivity**（Socket Mode 利用時も Request URL または Socket Mode で受信）が必要。
- 従来どおりスレッドへの「ア」〜「エ」単独返信でも採点可能。

## Verify

```bash
python -m pytest tests/test_quiz_blocks.py tests/test_slack_routing.py -q
```

Slack 上: `@FEbot 過去問` → 各選択肢横のボタンをクリック → 正誤・解説がスレッドに返ること。

## Rollback

`build_quiz_message` / `handle_quiz_button` / `@app.action` を削除し、`_format_quiz` によるプレーンテキスト出題に戻す。
