# 練習問題の Block Kit 整形（2026-06-09）

## Intent

`/fe-quiz 科目A` などの出題と、メンション/DM の「過去問」キーワード出題で、問題文が読みにくく、選択肢と回答操作が分かりにくかった。RAG 回答と同様に Block Kit で統一し、常に見やすく答えやすいレイアウトにする。

## Change

| ファイル | 内容 |
|---------|------|
| `src/febot/slack_handlers.py` | `build_quiz_message` を再設計。ヘッダーに科目、本文は `build_slack_blocks`、選択肢は `section` + 右側ボタン、回答方法は `section` で案内 |
| `src/febot/slack_app.py` | `/fe-quiz` が未実装の `_format_quiz` を参照していた不具合を修正。`build_quiz_message` + `sessions.set_quiz` に統一 |
| `README.md` | `/fe-quiz` の Block Kit 出題と Slash Commands 一覧を更新 |

### レイアウト（上から）

1. `header` — 例: `科目A 練習問題`
2. `context` — `qid` · 分野 · 種別
3. `divider`
4. 問題文 — コードブロック・箇条書き等は RAG と同じ `build_slack_blocks` 経路
5. `divider` + `*回答方法*` — 各選択肢右のボタンで回答する旨
6. 各選択肢 — `section`（太字ア〜エ + 本文）+ `accessory` ボタン（ア〜エ）

ブロック数が 50 を超える場合は本文を単一 `section` に畳むコンパクト版にフォールバック。

## Impact

- `/fe-quiz` スラッシュコマンドが正常に Block Kit で投稿・採点できる（従来は `_format_quiz` 未定義でエラーになり得た）。
- `@ボット /fe-quiz 科目B` のようにメンション付きで送っても RAG ではなくコーパス出題にルーティングする（従来は LLM が疑似問題を生成していた）。
- メンション/DM の「過去問」キーワード出題も同じレイアウト。
- 採点ロジック（`quiz_answer` アクション・スレッド返信）は変更なし。

## Verify

```bash
python3 -m pytest tests/test_quiz_blocks.py tests/test_slack_routing.py -q
```

Slack 上で `/fe-quiz 科目A` を実行し、問題文・選択肢・下部 4 ボタンが意図どおり表示されることを目視確認する。

## Rollback

`build_quiz_message` を旧実装（選択肢ごとの `section` + 右側ボタン）に戻し、`fe_quiz_cmd` の `chat_postMessage` をテキストのみに戻す。
