# AGENT.md 変更内容

## 変更の意図
- AI Agent が最初に読むべき情報を、FEbot 固有の実装・運用前提に合わせて一箇所に集約するため。
- 既存の 2 行メモでは、実行コマンドや環境変数ルール、参照先ドキュメントが不足していたため。

## 実装内容
- `AGENT.md` を全面更新し、以下を追加した。
  - 必読ファイル（`README.md`, `pyproject.toml`, 関連 docs）
  - プロジェクト前提（OpenAI 互換 API 前提、`llm.py` 未接続）
  - 実行コマンド（install / ingest / run / IPA fetch）
  - 環境変数ポリシー（秘密情報の直書き禁止、`.env` 管理）
  - 編集ルール（KISS / YAGNI / DRY）
  - 作業時チェックリスト（実行確認、ingest 再実行要否の明記）

## 具体例
- 例1: RAG 関連のコード変更時は、`scripts/ingest.py` の再実行が必要かどうかを PR や作業メモに明記する。
- 例2: 新しい必須環境変数を追加した場合は、`.env` ではなく `.env.example` にも追記して共有する。
