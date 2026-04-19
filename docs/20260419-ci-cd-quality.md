# CI/CD（コード品質ゲート）

## 意図

チーム開発でフォーマット・Lint・インストール可能性を自動検証し、人手レビューを補う。ワークフロー依存（Actions のみ pip で ruff を入れる等）ではなく、`pyproject.toml` の `[project.optional-dependencies] dev` を単一情報源として CI と揃える。

## 構成

| 項目 | 内容 |
|------|------|
| Lint / format | Ruff（`tool.ruff` で対象 Python とルールを固定） |
| テスト | pytest（`tests/`）。現状はパッケージ読み込みのスモークテスト |
| マルチバージョン | `test` ジョブで Python 3.10 / 3.12（`requires-python` の下限と現行安定の代表） |
| 並行実行の抑制 | `concurrency` で同一ブランチの古い実行をキャンセル |
| 依存の鮮度 | Dependabot（`pip` と `github-actions`） |

## デプロイ

既存の `deploy` ジョブは変更しない。品質ジョブ（`lint`・`test`）が成功した `main` への push のみ SSH デプロイする。

## メンテナンスの指針

- ルール追加は `pyproject.toml` の `[tool.ruff.lint]` で行い、ローカルで `python -m ruff check ...` と一致させる。
- テストは `tests/` に追加し、`pytest` が収集できるようにする。
- Actions のバージョンは Dependabot が週次で提案する。セキュリティパッチはマージ判断を優先する。
