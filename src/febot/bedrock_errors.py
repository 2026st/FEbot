"""Bedrock / IAM errors surfaced to Slack and content-filter fail-open."""

from __future__ import annotations

from botocore.exceptions import ClientError


def is_marketplace_access_denied(exc: BaseException) -> bool:
    """True when Bedrock denies access because AWS Marketplace actions are missing."""
    code, msg = _client_error_parts(exc)
    if code != "AccessDeniedException":
        return False
    lower = msg.lower()
    return "marketplace" in lower or "viewsubscriptions" in lower.replace(" ", "")


def slack_reply_for_bedrock_access_error(exc: BaseException) -> str | None:
    """Slack 向け短文。該当しない場合は None（汎用エラー文言にフォールバック）。"""
    if is_marketplace_access_denied(exc):
        return (
            "Bedrock のチャットモデルへのアクセスが拒否されました（*AWS Marketplace* 関連）。\n"
            "次のいずれかで対応してください。\n"
            "• IAM に `aws-marketplace:ViewSubscriptions`（必要なら `aws-marketplace:Subscribe`）を付与し、"
            "該当モデル／推論プロファイルの利用を有効化する\n"
            "• `BEDROCK_CHAT_MODEL_ID` を Marketplace 不要な in-region モデルに変更する（例: "
            "`anthropic.claude-3-5-haiku-20241022-v1:0`）\n"
            "詳細: README の Bedrock 節、`docs/20260514-bedrock-marketplace-access.md`。"
        )
    code, msg = _client_error_parts(exc)
    if code == "AccessDeniedException":
        return (
            "Bedrock へのアクセスが拒否されました（AccessDenied）。\n"
            "IAM の `bedrock:InvokeModel` / `bedrock:Converse`（利用している API に合わせる）と、"
            "Bedrock コンソールのモデルアクセス設定を確認してください。"
        )
    return None


def _client_error_parts(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, ClientError):
        err = exc.response.get("Error") or {}
        return str(err.get("Code") or ""), str(err.get("Message") or "")
    return "", str(exc)
