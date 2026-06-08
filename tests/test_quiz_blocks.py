"""Tests for quiz Block Kit message and button handling."""

from febot.quiz import QuizItem, parse_choice_lines
from febot.slack_handlers import build_quiz_message, handle_quiz_button
from febot.thread_session import ThreadSessionStore, thread_key


def test_parse_choice_lines() -> None:
    choices = (
        "**ア** 選択肢A\n"
        "**イ** 選択肢B\n"
        "**ウ** 選択肢C\n"
        "**エ** 選択肢D"
    )
    assert parse_choice_lines(choices) == [
        ("ア", "選択肢A"),
        ("イ", "選択肢B"),
        ("ウ", "選択肢C"),
        ("エ", "選択肢D"),
    ]


def test_build_quiz_message_has_choice_buttons() -> None:
    item = QuizItem(
        qid="q1",
        qtype="午前（擬似）",
        body="問題文です。",
        choices="**ア** A\n**イ** B\n**ウ** C\n**エ** D",
        correct="イ",
        explanation="解説",
    )
    fallback, blocks = build_quiz_message(item)
    assert "問題文" in fallback
    sections_with_buttons = [
        b for b in blocks if b.get("type") == "section" and "accessory" in b
    ]
    assert len(sections_with_buttons) == 4
    assert sections_with_buttons[0]["accessory"]["action_id"] == "quiz_answer"
    assert sections_with_buttons[0]["accessory"]["value"] == "ア"


def test_handle_quiz_button_grades_and_clears() -> None:
    sessions = ThreadSessionStore()
    channel = "C1"
    root = "100.0"
    key = thread_key(channel, root)
    item = QuizItem(
        qid="q1",
        qtype="単一",
        body="b",
        choices="**ア** a\n**イ** b",
        correct="イ",
        explanation="e",
    )
    sessions.set_quiz(key, item)
    replies: list[str] = []

    def say(msg: str, **kwargs) -> None:
        replies.append(msg)

    body = {
        "channel": {"id": channel},
        "message": {"ts": root, "thread_ts": None},
        "actions": [{"value": "イ"}],
    }
    assert handle_quiz_button(sessions, body, say) is True
    assert sessions.peek_quiz(key) is None
    assert len(replies) == 1
    assert "正解" in replies[0]
