"""Tests for Slack event routing helpers."""

from febot.quiz import QuizItem
from febot.slack_handlers import (
    ProcessedEvents,
    session_key,
    text_mentions_bot,
    try_handle_quiz_reply,
)
from febot.thread_session import ThreadSessionStore, thread_key, thread_root_ts_from_event


def test_session_key_matches_quiz_thread() -> None:
    channel = "C1"
    mention_ts = "111.111"
    mention_event = {"channel": channel, "ts": mention_ts}
    assert session_key(mention_event) == thread_key(channel, mention_ts)

    reply_event = {"channel": channel, "ts": "222.222", "thread_ts": mention_ts}
    assert thread_root_ts_from_event(reply_event) == mention_ts
    assert session_key(reply_event) == thread_key(channel, mention_ts)


def test_quiz_reply_strict_routes_to_rag_when_ambiguous() -> None:
    sessions = ThreadSessionStore()
    channel = "C1"
    root = "100.0"
    key = thread_key(channel, root)
    item = QuizItem(
        qid="q1",
        qtype="単一",
        body="b",
        choices="c",
        correct="イ",
        explanation="e",
    )
    sessions.set_quiz(key, item)
    replies: list[str] = []

    def say(msg: str, **kwargs) -> None:
        replies.append(msg)

    event = {"channel": channel, "ts": "101.0", "thread_ts": root}
    assert try_handle_quiz_reply(sessions, event, "なぜウが違う？", say) is False
    assert sessions.peek_quiz(key) is item
    assert replies == []

    assert try_handle_quiz_reply(sessions, event, "イ", say) is True
    assert sessions.peek_quiz(key) is None
    assert len(replies) == 1
    assert "正解" in replies[0]


def test_processed_events_dedupe() -> None:
    cache = ProcessedEvents(ttl_sec=60.0, max_size=10)
    cache.mark("C", "1.0")
    assert cache.was_processed("C", "1.0") is True
    assert cache.was_processed("C", "2.0") is False


def test_text_mentions_bot() -> None:
    assert text_mentions_bot("hi <@U123> there", "U123") is True
    assert text_mentions_bot("hi there", "U123") is False
    assert text_mentions_bot("hi", None) is False
