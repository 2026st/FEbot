# 練習問題データの配置（2026-06-09）

## Intent

2026-05-20 の RAG 向け `data/corpus/` 削除後、`/fe-quiz` が参照する問題ファイルも消え、出題 0 件になっていた。RAG コーパスと練習問題を分離する。

## Change

| 項目 | 内容 |
|------|------|
| `data/quiz/` | 練習問題専用ディレクトリ（Git 管理） |
| `QUIZ_DIR` | 既定 `./data/quiz`（`.env` で上書き可） |
| `load_quiz_items` | `CORPUS_DIR` ではなく `QUIZ_DIR` を読む |

### 同梱ファイル

- `sample-questions.md` — オリジナル 5 問（科目A 3 / 科目B 2）
- （任意）`ipa-fe-2023r05-cbt-kamoku-a-qs.md` + `-ans.md` — IPA 科目A 20 問

IPA ファイルは容量の都合で未同梱の場合、`git show a73a23a:data/corpus/ipa-fe-2023r05-cbt-kamoku-a-*.md` から `data/quiz/` へ復元できる。

## Impact

- `/fe-quiz 科目A` / `科目B` がコーパスから出題可能（ボット再起動後）
- RAG の `CORPUS_DIR` を空のまま維持できる

## Verify

```bash
python3 -c "from febot.config import Settings; from febot.quiz import load_quiz_items; s=Settings.load(require_slack=False); print(len(load_quiz_items(s.quiz_dir)))"
```

5 以上が返れば OK（IPA 復元時は 25 前後）。

## Rollback

`QUIZ_DIR` を未設定に戻し `load_quiz_items` を `corpus_dir` 参照に戻す（非推奨）。
