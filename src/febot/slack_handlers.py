"""Slack thread/quiz handlers (no RAG import — safe for unit tests)."""

from __future__ import annotations

import time
from collections import OrderedDict

from febot.quiz import QuizItem, normalize_quiz_reply
from febot.thread_session import ThreadSessionStore, thread_key, thread_root_ts_from_event

_PROCESSED_EVENT_TTL_SEC = 5.0
_PROCESSED_EVENT_MAX = 100

HELP_COMMANDS = frozenset({"help", "febot-help", "fe-help"})
_PERCENT_USAGE = "コマンド形式: `%help` または `%febot-help`（Slack では `/fe-help` も利用可）"
_UNKNOWN_COMMAND_TEMPLATE = "不明なコマンド: %{name}。利用可能: %help, %febot-help"


class ProcessedEvents:
    """Dedupe app_mention + message.channels for the same Slack message ts."""

    def __init__(
        self,
        *,
        ttl_sec: float = _PROCESSED_EVENT_TTL_SEC,
        max_size: int = _PROCESSED_EVENT_MAX,
    ) -> None:
        self._ttl = ttl_sec
        self._max_size = max_size
        self._seen: OrderedDict[tuple[str, str], float] = OrderedDict()

    def mark(self, channel: str, ts: str) -> None:
        key = (channel, ts)
        now = time.monotonic()
        self._seen[key] = now
        self._seen.move_to_end(key)
        self._evict(now)

    def was_processed(self, channel: str, ts: str) -> bool:
        key = (channel, ts)
        now = time.monotonic()
        self._evict(now)
        return key in self._seen

    def _evict(self, now: float) -> None:
        while self._seen:
            oldest_key, oldest_at = next(iter(self._seen.items()))
            if now - oldest_at <= self._ttl and len(self._seen) <= self._max_size:
                break
            self._seen.pop(oldest_key, None)
        while len(self._seen) > self._max_size:
            self._seen.popitem(last=False)


def parse_percent_command(text: str) -> str | None:
    """Return command name (lowercase) if text is a % command, else None. '%' alone -> ''."""
    stripped = text.strip()
    if not stripped.startswith("%"):
        return None
    body = stripped[1:].strip()
    if not body:
        return ""
    name, _, _ = body.partition(" ")
    return name.lower()


def try_handle_percent_command(
    text: str,
    *,
    help_text: str,
    say,
    thread_ts: str | None = None,
) -> bool:
    """Handle %prefixed commands. Returns True if handled."""
    name = parse_percent_command(text)
    if name is None:
        return False

    kwargs = {"thread_ts": thread_ts} if thread_ts else {}
    if name in HELP_COMMANDS:
        say(help_text, **kwargs)
        return True
    if name == "":
        say(_PERCENT_USAGE, **kwargs)
        return True
    say(_UNKNOWN_COMMAND_TEMPLATE.format(name=name), **kwargs)
    return True


def session_key(event: dict) -> str:
    return thread_key(event["channel"], thread_root_ts_from_event(event))


def text_mentions_bot(text: str, bot_user_id: str | None) -> bool:
    if not bot_user_id:
        return False
    return f"<@{bot_user_id}>" in text


def grade_quiz_answer(item: QuizItem, ans: str) -> str:
    if ans == item.correct:
        return f"正解です（{item.correct}）。\n*解説*: {item.explanation}"
    return f"不正解です。あなたの解答: {ans} / 正解: {item.correct}\n*解説*: {item.explanation}"


def try_handle_quiz_reply(
    sessions: ThreadSessionStore,
    event: dict,
    text: str,
    say,
) -> bool:
    """Handle strict quiz answer in thread. Returns True if handled (graded)."""
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return False
    key = session_key(event)
    item = sessions.peek_quiz(key)
    if item is None:
        return False

    ans = normalize_quiz_reply(text)
    if not ans:
        return False

    msg = grade_quiz_answer(item, ans)
    say(msg, thread_ts=thread_ts)
    sessions.clear_quiz(key)
    sessions.append_user(key, text)
    sessions.append_assistant(key, msg)
    return True
