"""Tests for multi-choice quiz (科目B ア〜ク)."""

from febot.quiz import QuizItem, normalize_quiz_reply, parse_choice_lines
from febot.slack_handlers import build_quiz_message, handle_quiz_button
from febot.thread_session import ThreadSessionStore, thread_key

_MARKS_B = ("ア", "イ", "ウ", "エ", "オ", "カ", "キ", "ク")


def test_normalize_quiz_reply_multichoice() -> None:
    assert normalize_quiz_reply("ク", allowed_marks=_MARKS_B) == "ク"
    assert normalize_quiz_reply("ク.", allowed_marks=_MARKS_B) == "ク"
    assert normalize_quiz_reply("イ", allowed_marks=_MARKS_B) == "イ"
    assert normalize_quiz_reply("クです", allowed_marks=_MARKS_B) is None


def test_parse_choice_lines_extended() -> None:
    choices = "**ア** a\n**ク** c\n**ケ** k"
    assert parse_choice_lines(choices) == [("ア", "a"), ("ク", "c"), ("ケ", "k")]


def test_build_quiz_message_multichoice_actions() -> None:
    choices = "\n".join(f"**{m}** choice {m}" for m in _MARKS_B)
    item = QuizItem(
        qid="ipa-2023r05-b-q02",
        qtype="科目B（IPA 2023r05 科目B）",
        body="問題文",
        choices=choices,
        correct="ク",
        explanation="解説",
        category="科目B",
    )
    _fallback, blocks = build_quiz_message(item)
    action_blocks = [b for b in blocks if b.get("type") == "actions"]
    assert len(action_blocks) >= 2
    all_values = []
    for ab in action_blocks:
        for el in ab.get("elements", []):
            all_values.append(el.get("value"))
    assert "ク" in all_values


def test_handle_quiz_button_ku() -> None:
    sessions = ThreadSessionStore()
    key = thread_key("C1", "100.0")
    choices = "\n".join(f"**{m}** x" for m in _MARKS_B)
    item = QuizItem(
        qid="q2",
        qtype="科目B",
        body="b",
        choices=choices,
        correct="ク",
        explanation="e",
        category="科目B",
    )
    sessions.set_quiz(key, item)
    replies: list[str] = []

    def say(msg: str, **kwargs) -> None:
        replies.append(msg)

    body = {
        "channel": {"id": "C1"},
        "message": {"ts": "100.0", "thread_ts": None},
        "actions": [{"value": "ク"}],
    }
    assert handle_quiz_button(sessions, body, say) is True
    assert "正解" in replies[0]
