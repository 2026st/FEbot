"""Tests for in-memory thread session store."""

from febot.quiz import QuizItem
from febot.thread_session import (
    ChatTurn,
    ThreadSessionStore,
    format_history_for_prompt,
    thread_key,
    thread_root_ts_from_event,
)


def test_thread_key_and_root_ts() -> None:
    assert thread_key("C1", "123.456") == "C1:123.456"
    event = {"ts": "100.001", "thread_ts": "99.000"}
    assert thread_root_ts_from_event(event) == "99.000"
    assert thread_root_ts_from_event({"ts": "100.001"}) == "100.001"


def test_history_trim() -> None:
    store = ThreadSessionStore(max_turns=3, max_sessions=10)
    key = "C:1"
    for i in range(5):
        store.append_user(key, f"u{i}")
    assert len(store.history_for_prompt(key)) == 3
    assert store.history_for_prompt(key)[0].text == "u2"


def test_quiz_set_clear() -> None:
    store = ThreadSessionStore()
    key = "C:thread_root"
    item = QuizItem(
        qid="q1",
        qtype="単一",
        body="body",
        choices="**ア** x",
        correct="ア",
        explanation="exp",
    )
    store.set_quiz(key, item)
    assert store.peek_quiz(key) is item
    assert store.is_bot_active(key)
    cleared = store.clear_quiz(key)
    assert cleared is item
    assert store.peek_quiz(key) is None


def test_format_history_for_prompt() -> None:
    turns = [
        ChatTurn(role="user", text="TCPとは"),
        ChatTurn(role="assistant", text="TCPは…"),
    ]
    out = format_history_for_prompt(turns)
    assert "ユーザー: TCPとは" in out
    assert "アシスタント: TCPは" in out


def test_channel_quiz_key_matches_reply_thread_ts() -> None:
    """Regression: quiz state must use thread parent ts, not bot message ts."""
    store = ThreadSessionStore()
    channel = "CCHAN"
    mention_ts = "111.111"
    thread_root = mention_ts
    key = thread_key(channel, thread_root)
    item = QuizItem(
        qid="q2",
        qtype="単一",
        body="b",
        choices="c",
        correct="イ",
        explanation="e",
    )
    store.set_quiz(key, item)
    reply_event = {"channel": channel, "ts": "222.222", "thread_ts": mention_ts}
    assert thread_root_ts_from_event(reply_event) == mention_ts
    assert store.peek_quiz(thread_key(channel, thread_root_ts_from_event(reply_event))) is item
