"""Tests for /fe-* message slash commands."""

from febot.slack_handlers import (
    KNOWN_SLASH_COMMANDS,
    parse_slash_command,
    try_handle_slash_command,
)


def test_parse_slash_command() -> None:
    assert parse_slash_command("/fe-help") == ("fe-help", "")
    assert parse_slash_command("/fe-quiz 科目B") == ("fe-quiz", "科目B")
    assert parse_slash_command("/FE-QUIZ a") == ("fe-quiz", "a")
    assert parse_slash_command("/fe-format-test") == ("fe-format-test", "")
    assert parse_slash_command("過去問") is None
    assert parse_slash_command("") is None


def test_known_slash_commands() -> None:
    assert frozenset({"fe-help", "fe-quiz", "fe-format-test"}) == KNOWN_SLASH_COMMANDS


def test_try_handle_slash_command_help() -> None:
    replies: list[str] = []

    def say(msg: str, **kwargs) -> None:
        replies.append(msg)

    assert try_handle_slash_command(
        "/fe-help",
        help_text="HELP",
        say=say,
        handle_quiz=lambda _args: None,
        handle_format_test=lambda: None,
    )
    assert replies == ["HELP"]


def test_try_handle_slash_command_quiz() -> None:
    quiz_args: list[str] = []

    def handle_quiz(args: str) -> None:
        quiz_args.append(args)

    assert try_handle_slash_command(
        "/fe-quiz 科目A",
        help_text="HELP",
        say=lambda *_a, **_k: None,
        handle_quiz=handle_quiz,
        handle_format_test=lambda: None,
    )
    assert quiz_args == ["科目A"]


def test_try_handle_slash_command_format_test() -> None:
    called = False

    def handle_format_test() -> None:
        nonlocal called
        called = True

    assert try_handle_slash_command(
        "/fe-format-test",
        help_text="HELP",
        say=lambda *_a, **_k: None,
        handle_quiz=lambda _args: None,
        handle_format_test=handle_format_test,
    )
    assert called


def test_try_handle_slash_command_unknown() -> None:
    replies: list[str] = []

    def say(msg: str, **kwargs) -> None:
        replies.append(msg)

    assert try_handle_slash_command(
        "/fe-unknown",
        help_text="HELP",
        say=say,
        handle_quiz=lambda _args: None,
        handle_format_test=lambda: None,
    )
    assert len(replies) == 1
    assert "/fe-unknown" in replies[0]


def test_try_handle_slash_command_not_command() -> None:
    assert (
        try_handle_slash_command(
            "質問",
            help_text="HELP",
            say=lambda *_a, **_k: None,
            handle_quiz=lambda _args: None,
            handle_format_test=lambda: None,
        )
        is False
    )


def test_try_handle_slash_command_slash_only() -> None:
    replies: list[str] = []

    def say(msg: str, **kwargs) -> None:
        replies.append(msg)

    assert try_handle_slash_command(
        "/",
        help_text="HELP",
        say=say,
        handle_quiz=lambda _args: None,
        handle_format_test=lambda: None,
    )
    assert len(replies) == 1
    assert "/fe-help" in replies[0]
