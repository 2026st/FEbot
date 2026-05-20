# FEのSlack RAG

## 目的とターゲット

1. 目的
基本情報技術者試験の合格を目指す学生に対し、効率的でわかりやすい学習環境を提供、および学習の習慣化をサポートする。

2. ターゲット
基本情報資格試験の取得を目指している学生(非情報系も含む)

## 機能要件

- 用語解説機能（コーパス RAG＋`glossary.md` の用語マッチブースト）
- 過去問・練習問題の出題（`data/corpus/sample-questions.md` をパース）
- 問題解説機能（スレッドで正誤と解説を返す。同一スレッド内の会話履歴をプロセス稼働中に保持）
- コーパスに該当がない質問は **DuckDuckGo 検索 → LLM で要約 → コーパスへ保存** し、次回以降はナレッジとして検索可能
- **コンテンツフィルター機能**（LLM を使って質問が IT・プログラミング関連かを判定し、無関係な質問をフィルタリング）

## 非機能要件

- 基本的に24時間365日稼働
- コストはできるだけ抑える

## データソース要件

- IPAが公開している過去問PDFやテキストデータ
- IPAの公式シラバス、またはオープンなIT用語辞典などのデータ

## システム構成・技術スタック

- **言語**: Python 3.10 以上（`pyproject.toml` の `requires-python` に準拠。`X | Y` 型表記のため 3.9 非対応）
- **Slack**: [slack-bolt](https://slack.dev/bolt-python/)（**Socket Mode**）
- **ベクトルDB**: Chroma（ローカル永続、`CHROMA_PATH`）
- **LLM / 埋め込み**: チャットは **Amazon Bedrock**（`USE_BEDROCK` または `BEDROCK_CHAT_MODEL_ID`）または **OpenAI 互換**（`AI_API_KEY`）。**埋め込み（ingest・RAG クエリ）は常に OpenAI 互換 API**（`AI_API_KEY`・`AI_EMBEDDING_MODEL` 等）。Bedrock 利用時も埋め込み用に `AI_API_KEY` が必要（詳細は `.env.example`）
- **Web 検索フォールバック**: `ddgs`（DuckDuckGo、API キー不要）
- **コーパス**: `data/corpus/*.md`。オリジナル教材に加え、IPA 公表 PDF から抽出した `ipa-*.md` を想定。利用上の留意点は [IPA FAQ（試験制度・その他）](https://www.ipa.go.jp/shiken/faq.html#seido) を確認すること。PDF の再取得・テキスト再生成は `python3 scripts/ipa_build_corpus.py --fetch`（詳細は [docs/20260405-ipa-corpus.md](docs/20260405-ipa-corpus.md)）。

OpenAI 互換 API からの移行手順・ベクトル次元の注意は [docs/20260513-bedrock-openai-replacement.md](docs/20260513-bedrock-openai-replacement.md) を参照。

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

   **RAG・ingest・Web 要約（Bedrock または OpenAI 互換）**

   - **バックエンドの優先**: `USE_BEDROCK=true`、または `BEDROCK_CHAT_MODEL_ID` を設定するとチャットは Bedrock。`USE_BEDROCK=false` で OpenAI 互換のみに固定。
   - **Bedrock（チャット）時**: AWS 認証、`AWS_REGION` または `AWS_DEFAULT_REGION`（既定 `ap-northeast-1`）、`BEDROCK_CHAT_MODEL_ID`（未設定時の既定は `anthropic.claude-3-5-haiku-20241022-v1:0`）。IAM の例: `bedrock:InvokeModel`、Converse 利用時は `bedrock:Converse`。**加えて埋め込み用に `AI_API_KEY`（および任意で `AI_BASE_URL`・`AI_EMBEDDING_MODEL`）が必須。** 東京リージョンで Claude Sonnet 4.6 など **geo 推論**のみの場合は、AWS のモデルカードに従い `BEDROCK_CHAT_MODEL_ID=jp.anthropic.claude-sonnet-4-6` のように **jp. 付き inference profile ID** を指定できるが、この場合は **AWS Marketplace 向け IAM**（`ViewSubscriptions` / `Subscribe`）が追加で必要になることがある（詳細は [docs/20260514-bedrock-chat-model-invalid.md](docs/20260514-bedrock-chat-model-invalid.md)、[docs/20260514-bedrock-marketplace-access.md](docs/20260514-bedrock-marketplace-access.md)）。
   - **OpenAI 互換のみ（Bedrock 未使用）**: `AI_API_KEY`、任意で `AI_BASE_URL`、`AI_CHAT_MODEL`（既定 `gpt-4o-mini`）、`AI_EMBEDDING_MODEL`（既定 `text-embedding-3-small`）
   - **埋め込み次元**: `AI_EMBEDDING_MODEL` を変えたら Chroma / pgvector の次元と一致させる。**モデルを変えたら `ingest` を再実行**すること。

   **任意（パス・検索チューニング）**

   - `CHROMA_PATH` … 既定 `./data/chroma`
   - `CORPUS_DIR` … 既定 `./data/corpus`
   - `RAG_TOP_K` … 参照チャンク数（既定 `5`）
   - `RAG_MAX_DISTANCE` … Chroma コサイン距離の上限（既定 `0.52`。`off` / `none` で無効化）
   - `RAG_POOL_MULT` … 距離フィルタ前に読む候補の倍率（既定 `5`）
   - `RATE_LIMIT_PER_MINUTE` … Slack ユーザーあたりの RAG 呼び出し上限（既定 `20`）
   - `WEB_SEARCH_MAX_RESULTS` … Web 検索の最大件数（既定 `5`）
   - `CONTENT_FILTER_ENABLED` … コンテンツフィルターの有効/無効（既定 `true`。IT・プログラミング関連以外の質問をフィルタリング）
   - `THREAD_HISTORY_MAX_TURNS` … スレッドあたりの会話履歴保持件数（既定 `10`。ボット再起動で消える）
   - `THREAD_MAX_SESSIONS` … インメモリで保持するスレッドセッション数の上限（既定 `500`）
   - `BEDROCK_CHAT_SKIP_CONVERSE` … `true` のときチャットは `InvokeModel` のみ（`Converse` を試さない。既定 `false`）
   - `SUPABASE_URL` / `SUPABASE_KEY` … Supabase 移行スクリプト利用時に必要（通常運用では任意）

   最小例（Bedrock チャット＋OpenAI 埋め込み。本番は IAM ロール推奨）:

   ```bash
   AWS_REGION=ap-northeast-1
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   BEDROCK_CHAT_MODEL_ID=anthropic.claude-3-5-haiku-20241022-v1:0
   # Sonnet 4.6 を東京で geo 推論する例: BEDROCK_CHAT_MODEL_ID=jp.anthropic.claude-sonnet-4-6
   AI_API_KEY=sk-...
   ```

   最小例（OpenAI 互換のみ）:

   ```bash
   AI_API_KEY=sk-...
   ```

3. （任意）IPA 由来コーパスを公式サイトから取り直す場合は、ネットワークのある環境で次を実行する。生成物は `data/corpus/ipa-*.md`（`data/ipa_raw/` は `.gitignore` 対象）。

   ```bash
   python3 scripts/ipa_build_corpus.py --fetch
   ```

4. RAG を使う場合は、AWS＋Bedrock チャット用設定に加え `AI_API_KEY`、または OpenAI 互換のみなら `AI_API_KEY` が揃ったうえで、コーパスを埋め込み Chroma を生成する（**埋め込みモデルを変えたら再 ingest が必要**）。

   ```bash
   python3 scripts/ingest.py
   ```

5. ボットを起動する。

   ```bash
   python3 -m febot
   ```

## PR 前の手順（チーム向け）

Pull Request を出す前に、メンバー各自が次まで行う。

1. **`main` を前提にする**  
   作業開始前に `main` を取り込み、`main`（またはチーム決めの既定ブランチ）から作業用ブランチを切る。レビュー依頼時点でもベースとの差分が読みやすいように、不要なマージコミットや無関係な変更を混ぜない。

2. **秘密情報をリポジトリに載せない**  
   `.env` はコミットしない（`.gitignore` 済みであることを確認する）。パスワードや API キーをソースに直接書かず、環境変数や既存の設定ロード経由に統一する。

3. **CI と同じ品質チェックをローカルで通す**  
   次の「CI（品質ゲート）を通す手順」のコマンドがすべて成功した状態で PR を出す。失敗しているチェックはレビュー対象にしない。

4. **セルフレビューする**  
   `git diff` で自分の変更を読み直し、デバッグ用の `print`、コメントアウトの残骸、意図しないファイル追加がないか確認する。

5. **PR 本文を書く**  
   変更の目的と概要、動作確認で実施したこと（例: ボット起動、該当コマンド実行）、レビュアーへ伝えたい注意があれば記載する。仕様議論が必要ならドラフト PR にするか、本文で明示する。

## CI（品質ゲート）を通す手順

PR がマージ可能になるには、GitHub Actions（`.github/workflows/ci-cd.yml`）と同じ基準をローカルでも満たすことが前提となる。

- `ruff check` / `ruff format --check` 対象: `src/`、`scripts/`、`tests/`
- `pytest`（複数 Python バージョンはワークフロー参照）

```bash
python3 -m pip install -e ".[dev]"
python3 -m ruff format src/ scripts/ tests/
python3 -m ruff check src/ scripts/ tests/
python3 -m pytest
```

## 実行時の挙動（要約）

- **チャンネル**: ボットに **メンション**して質問。キーワード「過去問」「出題」「練習問題」で `sample-questions.md` から問題を出題し、**スレッド**で「ア」「イ」「ウ」「エ」に返信すると正誤と解説。
- **スレッド追質問**: ボットが一度応答したスレッドでは、メンションなしで追質問できる（会話履歴はプロセス稼働中のみ。再起動でリセット）。
- **DM**: メンション不要。上記キーワードと RAG 質問が同様に使える。
- **ヘルプ（`%` コマンド）**: メッセージ先頭が `%` のときコマンドとして扱う。`%help` / `%febot-help` で利用ガイドを表示（チャンネルでは @ボット と併用）。スラッシュ `/fe-help` も利用可。
- **RAG**: Chroma で類似チャンクを取得（距離しきい値・`glossary.md` ブーストあり）。埋め込みモデルを変えた場合は `RAG_MAX_DISTANCE` の再調整が必要になることがある。LLM が「参照抜粋にない」と判断した場合や、検索ヒットが無い場合は **Web 検索フォールバック**に進み、取得内容をコーパスに追記してから回答する。

## Slack アプリ側（概要）

- **Socket Mode** をオンにする。
- **Bot Token Scopes** の例: `app_mentions:read`, `chat:write`, `channels:history`, `im:history`（DM 利用時）
- **プライベートチャンネル**でもスレッド追質問・採点を使う場合: `groups:history` と Event `message.groups` を追加
- **Event Subscriptions**（必須）: `app_mention`, `message.channels`（スレッド追質問・練習問題の解答）, `message.im`
- **Slash Commands**: `/fe-help`（メッセージの `%help` / `%febot-help` と同等）

### デプロイ後チェックリスト

1. 上記 Event / Scope が Slack アプリに登録されていること（`message.channels` が無いと追質問・採点が届かない）
2. ボットプロセスを再起動し、`feat/#31` 以降のビルドが動いていること
3. チャンネルで `@FEbot 過去問` → スレッドに `イ` → 正誤。続けてメンションなしで追質問できること
