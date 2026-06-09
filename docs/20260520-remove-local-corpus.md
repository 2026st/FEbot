# ローカル corpus 削除（2026-05-20）

## 背景

IPA 公表 PDF から機械抽出した `data/corpus/ipa-*.md` および Web 検索キャッシュが RAG の参照抜粋を汚染し、初学者向けの丁寧な説明が得にくくなっていた。

## 実施内容

- `data/corpus/` ディレクトリ一式を削除
- `data/ipa_manifest.yaml` および corpus 生成・ingest 用スクリプト（`ipa_build_corpus.py`, `ingest.py`, `migrate_to_supabase.py`, `extract_syllabus_yogo.py`）を削除
- Web 検索後のローカルファイル保存（`data/corpus/`）を廃止
- Web 検索後のベクトル DB 自動追記（`add_to_corpus`）は **Supabase / Chroma のみ**（ローカル Markdown は書かない）
- `glossary.md` 用語マッチブーストを廃止

## 維持しているもの

- **ベクトル RAG**（Chroma または Supabase の `corpus_*` テーブル）による検索と回答生成
- RAG 未ヒット時の **DuckDuckGo Web 検索フォールバック**

## ベクトル DB の汚染を解消する場合

ローカル Markdown を消しても、既存の Chroma / Supabase には過去 ingest 分が残る。

### Chroma（既定）

```bash
# ボット停止後
rm -rf data/chroma
```

起動時に `febot_corpus` コレクションが無いとエラーになる。新しいデータソースで ingest スクリプトを用意するまで、Supabase を使うか、空のままでは RAG 応答不可（Web フォールバックのみ）。

### Supabase

`corpus_chunks` / `corpus_documents` を管理者が truncate または全削除する。

## 将来の ingest

新しい教材ソースが決まったら、Markdown 等からベクトル DB へ投入する ingest 手段を別途実装する（旧 `scripts/ingest.py` はローカル `data/corpus/` 前提のため削除済み）。
