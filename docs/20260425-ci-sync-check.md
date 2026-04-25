# CI 同期チェック導入

## Intent

AI 駆動開発で発生する、実装と `README.md` / `.env.example` の乖離を CI で自動検知する。

## Change

- `scripts/check_sync.py` を追加
  - コード上で参照される環境変数を静的抽出
  - `.env.example` のキー定義と突合
  - `README.md` の環境変数記載と突合
  - 不整合があれば非0終了でCIをfail
- `.github/workflows/ci-cd.yml` の `lint` job に同期チェックを追加
  - `python scripts/check_sync.py`
- 同期のためにドキュメントを補正
  - `.env.example` に `RATE_LIMIT_PER_MINUTE` を追加
  - `.env.example` の `AWS_BEARER_TOKEN_BEDROCK` をコメント化（現行未使用）
  - `README.md` に `SUPABASE_URL` / `SUPABASE_KEY` を明記

## Impact

- 実装で使っている環境変数の追記漏れをPR段階で検知できる。
- README記載漏れをCIで検知し、運用ドリフトを抑制できる。

## Verify

- `python3 scripts/check_sync.py` が成功することを確認。
- `python3 -m ruff check scripts/check_sync.py` が成功することを確認。

## Rollback

次を元に戻せばロールバック可能:

- `scripts/check_sync.py`
- `.github/workflows/ci-cd.yml` の同期チェック step
- `.env.example` / `README.md` の補正差分
