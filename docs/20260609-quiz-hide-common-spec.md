# 練習問題出題時の共通仕様（抜粋）非表示

## Intent

`/fe-quiz 科目A` / `科目B` の出題で、問題文末尾に付いていた「【共通仕様（抜粋）】」セクションが不要だった。科目B の擬似言語問題でも、出題画面では問題本文と選択肢だけを見せたい。

## Change

| ファイル | 内容 |
|---------|------|
| `src/febot/quiz.py` | `strip_quiz_common_spec` を追加。本文末尾の共通仕様ブロックを除去 |
| `src/febot/slack_handlers.py` | `build_quiz_message` / `format_quiz_history` で表示用本文に適用 |
| `src/febot/ipa_extract.py` | IPA 取り込み時に `body` へ共通仕様を連結しない（`appendix` フィールドのみ保持） |

## Impact

- Slack 出題（`/fe-quiz`・「過去問」キーワード）で共通仕様セクションは表示されない。
- Supabase に既に共通仕様付きで保存された `body` も、表示時に自動で除去される。
- 採点・解説ロジックは変更なし。

## Verify

```bash
python3 -m pytest tests/test_quiz_blocks.py tests/test_ipa_extract.py -q
```

## Rollback

`strip_quiz_common_spec` の呼び出しを外し、`ipa_extract.py` で `body` への連結を復元する。
