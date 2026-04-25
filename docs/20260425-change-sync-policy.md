# Change Sync Policy 導入メモ

## Intent

AI 駆動開発で発生しやすい、実装と `README.md` / `.env.example` の乖離を防ぐ。
ツール依存ではなく、リポジトリ運用で統一する。

## Change

- `.claude/skills/change-sync-Policy/SKILL.md` を全面リライト
  - 変更トリガー別の更新対象ファイルを明確化
  - `File Writing Rules` と `DoD` を追加
  - Cursor / Claude / VSCode でも同一ルールで運用できる記述に変更
- `CLAUDE.md` を新規追加
  - Claude 利用者向けの最小運用ルールを定義
- `.github/pull_request_template.md` を新規追加
  - エディタ非依存で最終チェックを強制

## Impact

- 実装変更時に、説明ファイル更新漏れがレビュー段階で検知しやすくなる。
- メンバーが使用ツールに関係なく、同一の同期ポリシーを適用できる。

## Verify

- `change-sync-Policy` に以下が含まれることを確認:
  - Change Matrix
  - File Writing Rules
  - DoD
  - Commit Gate
  - Shared Team Enforcement
- `CLAUDE.md` と PRテンプレートがリポジトリに存在することを確認。

## Rollback

次を削除または元に戻せばロールバック可能:

- `.claude/skills/change-sync-Policy/SKILL.md`
- `CLAUDE.md`
- `.github/pull_request_template.md`
- `docs/20260425-change-sync-policy.md`
