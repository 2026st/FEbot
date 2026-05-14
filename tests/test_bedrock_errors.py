"""Unit tests for Bedrock IAM / Marketplace error helpers."""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError

from febot.bedrock_errors import (
    is_marketplace_access_denied,
    slack_reply_for_bedrock_access_error,
)


def _access_denied(message: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": message}},
        "Converse",
    )


def test_marketplace_denied_detected() -> None:
    exc = _access_denied(
        "Model access is denied due to IAM user or service role is not authorized "
        "to perform the required AWS Marketplace actions (aws-marketplace:ViewSubscriptions)"
    )
    assert is_marketplace_access_denied(exc) is True
    reply = slack_reply_for_bedrock_access_error(exc)
    assert reply is not None
    assert "Marketplace" in reply
    assert "BEDROCK_CHAT_MODEL_ID" in reply


def test_marketplace_denied_message_variant() -> None:
    exc = _access_denied("Your AWS Marketplace subscription for this model cannot be completed")
    assert is_marketplace_access_denied(exc) is True


def test_non_marketplace_access_denied() -> None:
    exc = _access_denied("User is not authorized to perform: bedrock:InvokeModel")
    assert is_marketplace_access_denied(exc) is False
    reply = slack_reply_for_bedrock_access_error(exc)
    assert reply is not None
    assert "InvokeModel" in reply or "Bedrock" in reply


def test_wrong_error_code() -> None:
    exc = ClientError(
        {"Error": {"Code": "ValidationException", "Message": "bad"}},
        "Converse",
    )
    assert is_marketplace_access_denied(exc) is False
    assert slack_reply_for_bedrock_access_error(exc) is None


@pytest.mark.parametrize(
    "msg",
    [
        "something failed",
        "",
    ],
)
def test_plain_exception_not_marketplace(msg: str) -> None:
    assert is_marketplace_access_denied(RuntimeError(msg)) is False
    assert slack_reply_for_bedrock_access_error(RuntimeError(msg)) is None
