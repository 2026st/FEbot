# FEのSlack RAG

## 目的とターゲット

1. 目的
基本情報技術者試験の合格を目指す学生に対し、効率的でわかりやすい学習環境を提供、および学習の習慣化をサポートする。

2. ターゲット
基本情報資格試験の取得を目指している学生(非情報系も含む)

## 機能要件

- 用語解説機能（コーパス RAG＋`glossary.md` の用語マッチブースト）
- 過去問・練習問題の出題（`data/corpus/sample-questions.md` をパース）
- 問題解説機能（スレッドで正誤と解説を返す）
- コーパスに該当がない質問は **DuckDuckGo 検索 → LLM で要約 → コーパスへ保存** し、次回以降はナレッジとして検索可能

## 非機能要件

- 基本的に24時間365日稼働
- コストはできるだけ抑える

## データソース要件

- IPAが公開している過去問PDFやテキストデータ
- IPAの公式シラバス、またはオープンなIT用語辞典などのデータ

## システム構成・技術スタック

- **言語**: Python 3.9 以上（`pyproject.toml` の `requires-python` に準拠）
- **Slack**: [slack-bolt](https://slack.dev/bolt-python/)（**Socket Mode**）
- **ベクトルDB**: Chroma（ローカル永続、`CHROMA_PATH`）
- **LLM / 埋め込み**: **OpenAI 互換 API**（`openai` クライアント）。`AI_API_KEY` と任意の `AI_BASE_URL`（Azure 等）
- **Web 検索フォールバック**: `ddgs`（DuckDuckGo、API キー不要）
- **コーパス**: `data/corpus/*.md`。オリジナル教材に加え、IPA 公表 PDF から抽出した `ipa-*.md` を想定。利用上の留意点は [IPA FAQ（試験制度・その他）](https://www.ipa.go.jp/shiken/faq.html#seido) を確認すること。PDF の再取得・テキスト再生成は `python3 scripts/ipa_build_corpus.py --fetch`（詳細は [docs/20260405-ipa-corpus.md](docs/20260405-ipa-corpus.md)）。

補足: リポジトリには Bedrock 向けの `src/febot/llm.py` と移行メモ [docs/20260416-bedrock-migration.md](docs/20260416-bedrock-migration.md) があるが、**現行の `config.py` / `rag.py` / `scripts/ingest.py` は OpenAI 互換 API 前提**で、`llm.py` は応答パイプラインに未接続である。

## セットアップ・起動

1. 仮想環境を有効化し、依存を入れる（`pip` が無い場合は `python3 -m pip` を使う）。

   ```bash
   cd /path/to/FEbot
   python3 -m venv .venv
   source .venv/bin/activate   # Windows は .venv\Scripts\activate
   python3 -m pip install --upgrade pip
   python3 -m pip install -e .
   ```

   リポジトリ外で `pip3 install` だけ実行すると「インストール対象が無い」エラーになる。必ず上記のように **プロジェクトルートで** `-e .` を付ける。

   Web 検索フォールバックを使う場合は **`ddgs` が必要**（`pyproject.toml` のコア依存には含まれていない）。`requirements.txt` と揃えるなら次を併用する。

   ```bash
   python3 -m pip install -r requirements.txt
   ```

2. `.env.example` を `.env` にコピーし、値を設定する。

   **必須（Slack 起動）**

   - `SLACK_TOKEN` … Bot User OAuth Token（`xoxb-`）
   - `SLACK_APP_TOKEN` … App-Level Token（Socket Mode 用、`xapp-`）

   **RAG・ingest・Web 要約（OpenAI 互換 API）**

   - `AI_API_KEY` … 未設定の場合、Slack 接続・`/fe-help`・練習問題は動くが **埋め込み検索による回答と ingest は無効**
   - `AI_BASE_URL` … 省略時は OpenAI 公式。Azure 等はベース URL を指定
   - `AI_CHAT_MODEL` … 既定 `gpt-4o-mini`
   - `AI_EMBEDDING_MODEL` … 既定 `text-embedding-3-small`

   **任意（パス・検索チューニング）**

   - `CHROMA_PATH` … 既定 `./data/chroma`
   - `CORPUS_DIR` … 既定 `./data/corpus`
   - `RAG_TOP_K` … 参照チャンク数（既定 `5`）
   - `RAG_MAX_DISTANCE` … Chroma コサイン距離の上限（既定 `0.52`。`off` / `none` で無効化）
   - `RAG_POOL_MULT` … 距離フィルタ前に読む候補の倍率（既定 `5`）
   - `RATE_LIMIT_PER_MINUTE` … Slack ユーザーあたりの RAG 呼び出し上限（既定 `20`）
   - `WEB_SEARCH_MAX_RESULTS` … Web 検索の最大件数（既定 `5`）

   最小例（OpenAI 互換）:

   ```bash
   AI_API_KEY=sk-...
   AI_CHAT_MODEL=gpt-4o-mini
   AI_EMBEDDING_MODEL=text-embedding-3-small
   ```

3. （任意）IPA 由来コーパスを公式サイトから取り直す場合は、ネットワークのある環境で次を実行する。生成物は `data/corpus/ipa-*.md`（`data/ipa_raw/` は `.gitignore` 対象）。

   ```bash
   python3 scripts/ipa_build_corpus.py --fetch
   ```

4. RAG を使う場合は、`AI_API_KEY` 設定後にコーパスを埋め込み、Chroma を生成する。

   ```bash
   python3 scripts/ingest.py
   ```

5. ボットを起動する。

   ```bash
   python3 -m febot
   ```

## 実行時の挙動（要約）

- **チャンネル**: ボットに **メンション**して質問。キーワード「過去問」「出題」「練習問題」で `sample-questions.md` から問題を出題し、**スレッド**で「ア」「イ」「ウ」「エ」に返信すると正誤と解説。
- **DM**: メンション不要。上記キーワードと RAG 質問が同様に使える。
- **RAG**: Chroma で類似チャンクを取得（距離しきい値・`glossary.md` ブーストあり）。LLM が「参照抜粋にない」と判断した場合や、検索ヒットが無い場合は **Web 検索フォールバック**に進み、取得内容をコーパスに追記してから回答する。

## Slack アプリ側（概要）

- **Socket Mode** をオンにする。
- **Bot Token Scopes** の例: `app_mentions:read`, `chat:write`, `channels:history`, `im:history`（DM 利用時）
- **Event Subscriptions**: `app_mention`, `message.channels`（チャンネルスレッドでの解答用）, `message.im`
- **Slash Commands**: `/fe-help`
