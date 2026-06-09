# IPA 過去問の Supabase 取り込みと出題（2026-06-09）

## Intent

`/fe-quiz` の練習問題を IPA 公式 CBT 過去問に近づける。RAG 用 `corpus_*` と混ぜず、専用テーブル `quiz_*` にタグ付きで保存する。

## 構成

| 項目 | 内容 |
|------|------|
| スキーマ | `supabase/migrations/20260609_quiz_tables.sql` |
| ingest CLI | `scripts/ipa_ingest_quiz.py` |
| manifest | `data/ipa_quiz_manifest.yaml` |
| ランタイム | `SupabaseQuizStore` → `load_quiz_items_from_supabase()` |
| 図表 | PyMuPDF で PDF ページを PNG 化 → Storage `quiz-assets` |

## 初回セットアップ

1. Supabase SQL Editor でマイグレーションを適用
2. `.env` に `SUPABASE_URL`, `SUPABASE_KEY`（ボット読取）, `SUPABASE_SERVICE_KEY`（ingest 書込）
3. 依存: `pip install -e ".[ingest]"`（図表キャプチャに PyMuPDF）
4. ingest:

```bash
python scripts/ipa_ingest_quiz.py ingest --all
python scripts/ipa_ingest_quiz.py verify --exam-id 2025r07 --kamoku B
```

manifest 登録済み試験（2026-06-09 時点）: `2023r05`, `2024r06`, `2025r07`（各科目 A/B、CBT 公開分で 1 回あたり 26 問）

## コマンド

| コマンド | 説明 |
|----------|------|
| `discover [--write]` | IPA 公開一覧から新試験候補を表示 |
| `ingest --exam-id ID --kamoku A\|B` | 1試験を ingest |
| `ingest --all [--force]` | manifest 全件 |
| `verify --exam-id ID --kamoku A\|B` | 問数・図表タグを確認 |

オプション: `--skip-figures`（図表 PNG 生成省略）, `--skip-repair`（LLM 補正省略）

LLM 補正は **常に OpenAI 互換 API**（`AI_API_KEY` / `AI_CHAT_MODEL` / 任意 `AI_BASE_URL`）。ボットの RAG チャットが Bedrock でも ingest 補正は Bedrock を使わない。

## 新しい過去問の追加

1. IPA 公式ページから PDF URL を確認
2. `data/ipa_quiz_manifest.yaml` に `exam_id` / `kamoku` / `pdf_qs` / `pdf_ans` を追加
3. `python scripts/ipa_ingest_quiz.py ingest --exam-id <ID> --kamoku <A|B>`

## タグ（RAG との差別化）

- `quiz_questions.tags`: `quiz`, `ipa`, `exam_2023r05`, `kamoku_a`, `has_figure`, `source_ipa_official`
- `source_type`: `ipa_official`（ベクトル DB 非投入）

## 制限

- 図表は初版では**ページ単位の PNG レンダリング**（精密 crop は未対応。旧 Playwright は `file://` PDF で失敗するため PyMuPDF に変更）
- **科目B** は PDF 上の「問N」からページ範囲を特定し、問題文は **PNG のみ** Slack 表示（`body` は空、選択肢はテキストのまま）
- **科目A** は図表・真理値表・表組み等を検出した問題のみ PDF ページ PNG を付与。Slack では **テキスト＋画像**（通常問題はテキストのみ）
- PDF テキスト品質が低い場合は LLM 補正（`AI_API_KEY` 必須、`AI_CHAT_MODEL` 等。Bedrock ではなく OpenAI 互換 API 固定）
- ボット起動には Supabase に 1 件以上の問題が必要

## Verify

```bash
python3 -m pytest tests/test_ipa_extract.py tests/test_quiz_multichoice.py tests/test_supabase_quiz.py -q
```
