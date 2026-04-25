# CLAUDE.md (FEbot 共通運用)

このファイルは、Claude を使う開発者向けの最小運用ルール。
目的は、AI変更時の実装とドキュメントの乖離防止。

## 必読

- `README.md`
- `.claude/skills/change-sync-Policy/SKILL.md`
- `AGENT.md`

## MUST

1. 実装変更時は、同一タスクで関連ドキュメントを更新する。
2. 環境変数を変えたら `.env.example` と `README.md` を必ず同期する。
3. 非自明な変更は `docs/[YYYYMMDD]-[title].md` を更新する。
4. 機密値は `.env` のみで管理し、Git追跡ファイルに含めない。

## コミット前チェック

- `README.md` / `.env.example` / 実装に矛盾がない
- 不要なデバッグコードがない
- 変更理由と影響が必要なら `docs/` に記録済み
