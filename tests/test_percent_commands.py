"""Tests for %prefixed Slack message commands."""

from febot.slack_handlers import (
    HELP_COMMANDS,
    parse_percent_command,
    try_handle_percent_command,
)


def test_parse_percent_command_help() -> None:
    assert parse_percent_command("%help") == "help"
    assert parse_percent_command("  %febot-help  ") == "febot-help"
    assert parse_percent_command("%fe-help extra") == "fe-help"
    assert parse_percent_command("%") == ""
    assert parse_percent_command("質問") is None
    assert parse_percent_command("") is None


def test_help_commands_registered() -> None:
    assert frozenset({"help", "febot-help", "fe-help"}) == HELP_COMMANDS


def test_try_handle_percent_command_help() -> None:
    replies: list[tuple[str, dict]] = []

    def say(msg: str, **kwargs) -> None:
        replies.append((msg, kwargs))

    assert try_handle_percent_command(
        "%help",
        help_text="HELP_BODY",
        say=say,
        thread_ts="1.0",
    )
    assert len(replies) == 1
    assert replies[0] == ("HELP_BODY", {"thread_ts": "1.0"})


def test_try_handle_percent_command_unknown() -> None:
    replies: list[str] = []

    def say(msg: str, **kwargs) -> None:
        replies.append(msg)

    assert try_handle_percent_command(
        "%foo",
        help_text="HELP",
        say=say,
    )
    assert len(replies) == 1
    assert "不明なコマンド" in replies[0]
    assert "%foo" in replies[0]


def test_try_handle_percent_command_not_command() -> None:
    replies: list[str] = []

    def say(msg: str, **kwargs) -> None:
        replies.append(msg)

    assert (
        try_handle_percent_command(
            "通常の質問",
            help_text="HELP",
            say=say,
        )
        is False
    )
    assert replies == []


def test_try_handle_percent_command_empty() -> None:
    replies: list[str] = []

    def say(msg: str, **kwargs) -> None:
        replies.append(msg)

    assert try_handle_percent_command("%", help_text="HELP", say=say)
    assert len(replies) == 1
    assert "%help" in replies[0]
