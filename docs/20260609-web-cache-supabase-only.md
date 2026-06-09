# Web 検索キャッシュの Supabase 専用保存

## Intent

ナレッジは Supabase（または Chroma）に保持するため、`web_cache_*.md` を `data/corpus/` に残さない。

## Change

- `RagEngine.add_to_corpus` を復活。ベクトル DB への chunk / embed / upsert のみ行い、ローカルファイルは書かない
- `web_search.build_answer` が `(slack_text, corpus_md)` を返す形に戻した
- RAG 回答の出典 URL 抽出は Supabase の `corpus_documents.content` から行う（`citation_urls_for_source`）

## Impact

- Web 検索フォールバック後、同じ質問は次回から RAG でヒットしうる（Supabase / Chroma 利用時）
- `data/corpus/web_cache_*.md` は新規作成されない
- 既存のローカル `web_cache_*.md` は手動削除してよい（Supabase に投入済みなら RAG に影響しない）

## Verify

```bash
python3 -m pytest tests/test_web_search_corpus.py -q
python3 scripts/ci_local.py
```

## Rollback

`add_to_corpus` 呼び出しを `slack_app.py` から削除し、README の Web フォールバック説明を元に戻す。
