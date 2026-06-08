# Slack 回答の mrkdwn / Block Kit 整形

## 背景

LLM は GitHub 風 Markdown（`#` 見出し、`**` 太字、`|` テーブル）を出力しがちだが、Slack は標準 Markdown を解釈しない。通知・スレッド上で読みにくかったため、投稿前に Slack 向けへ変換する。

## 実装

| ファイル | 役割 |
|---------|------|
| `src/febot/slack_format.py` | Markdown → mrkdwn、Block Kit 組み立て |
| `src/febot/slack_app.py` | `_say_formatted` で RAG / Web 回答を投稿 |
| `src/febot/rag.py` / `web_search.py` | `SLACK_OUTPUT_RULES` をシステムプロンプトに付与 |

## 変換ルール（概要）

- `#` / `##` 見出し、`【見出し】` → Block Kit `header`（150 文字まで）
- `**bold**` → `*bold*`（mrkdwn 太字）。日本語直後の全角文字で太字が崩れる場合は `fix_slack_mrkdwn` で閉じ `*` の後にスペースを挿入
- 行全体の `*bold*` や箇条書き（`-` / `•`）→ `rich_text` ブロック（`style.bold` / `rich_text_list`）。**mrkdwn の `section` だけではリストと太字が表示されないことがある**
- インライン `` `code` `` → `rich_text` では `style.code: true`（バッククォート文字列のままでは表示されない）。単純な本文のみのときは `section` + mrkdwn のバッククォート
- `1. 項目` → `rich_text_list` の `style: ordered`
- `__下線__` → `rich_text` の `style.underline`（mrkdwn では未対応）
- 単純な本文のみ → `section` + `type: mrkdwn`
- `[label](url)` → `<url|label>`
- `---` → `divider` ブロック
- Markdown テーブル → `section` 内の fenced code（```）
- `【出典】` / `【出典URL】` 節 → `context` ブロック（URL は `<url>`）
- 本文 section は 3000 文字超で分割

## フォールバック

- Block が 50 個超: blocks を捨て、mrkdwn 単一 `text` のみ投稿（ログ警告）
- `say(text, blocks=...)` の `text` は通知用フォールバック（先頭 4000 文字）

## 会話履歴

`ThreadSessionStore` には Block JSON ではなく、`format_reply_for_history` で作った mrkdwn プレーンテキストを保存する（LLM への履歴注入用）。

## コーパス保存

Web 検索フォールバックの `corpus_md` は従来どおり Markdown のまま（Slack 変換の対象外）。

## 検証

```bash
python -m pytest tests/test_slack_format.py -q
```

Slack 上で見出し・太字・表・コードブロック・出典が意図どおりか目視確認する。

### Slack 上の表示テスト（ボット起動後）

| 方法 | 例 |
|------|-----|
| Slash Command | `/fe-format-test`（Slack アプリにコマンド登録が必要） |
| メンション | `@FEbot フォーマットテスト` または `@FEbot 表示テスト` |
| DM | `フォーマットテスト` |

固定サンプル（量子鍵配送風）を RAG と同じ `build_slack_blocks` 経路で投稿する。AI・RAG・ingest は不要。
