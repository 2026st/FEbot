"""In-memory per-thread conversation state (Slack thread / DM session)."""

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass, field

from febot.quiz import QuizItem

DEFAULT_MAX_TURNS = 10
DEFAULT_MAX_SESSIONS = 500


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "user" | "assistant"
    text: str


@dataclass
class ThreadSession:
    history: list[ChatTurn] = field(default_factory=list)
    pending_quiz: QuizItem | None = None
    bot_active: bool = False


def thread_key(channel_id: str, thread_root_ts: str) -> str:
    return f"{channel_id}:{thread_root_ts}"


def thread_root_ts_from_event(event: dict) -> str:
    return event.get("thread_ts") or event["ts"]


def format_history_for_prompt(turns: list[ChatTurn]) -> str:
    lines: list[str] = []
    for turn in turns:
        label = "ユーザー" if turn.role == "user" else "アシスタント"
        lines.append(f"{label}: {turn.text}")
    return "\n".join(lines)


def embed_query_text(
    question: str,
    history: list[ChatTurn] | None = None,
    *,
    max_len: int = 500,
) -> str:
    """Build text for vector search; include last user turn when follow-up is short."""
    if not history:
        return question
    last_user: str | None = None
    for turn in reversed(history):
        if turn.role == "user":
            last_user = turn.text
            break
    if not last_user or last_user.strip() == question.strip():
        return question
    combined = f"{last_user}\n{question}"
    if len(combined) > max_len:
        return combined[-max_len:]
    return combined


def build_user_content_with_history(
    *,
    question: str,
    context: str,
    history: list[ChatTurn] | None = None,
    question_heading: str = "【ユーザーの質問】",
    context_heading: str = "【参照抜粋】",
) -> str:
    blocks: list[str] = []
    if history:
        blocks.append(f"【これまでの会話】\n{format_history_for_prompt(history)}")
    blocks.append(f"{question_heading}\n{question}")
    blocks.append(f"{context_heading}\n{context}")
    return "\n\n".join(blocks)


def _max_turns() -> int:
    raw = os.environ.get("THREAD_HISTORY_MAX_TURNS", "").strip()
    if not raw:
        return DEFAULT_MAX_TURNS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_TURNS


def _max_sessions() -> int:
    raw = os.environ.get("THREAD_MAX_SESSIONS", "").strip()
    if not raw:
        return DEFAULT_MAX_SESSIONS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_SESSIONS


class ThreadSessionStore:
    """Thread-scoped history and quiz state (process lifetime only)."""

    def __init__(self, *, max_turns: int | None = None, max_sessions: int | None = None) -> None:
        self._max_turns = max_turns if max_turns is not None else _max_turns()
        self._max_sessions = max_sessions if max_sessions is not None else _max_sessions()
        self._sessions: OrderedDict[str, ThreadSession] = OrderedDict()

    def get(self, key: str) -> ThreadSession:
        if key in self._sessions:
            self._sessions.move_to_end(key)
            return self._sessions[key]
        self._evict_if_needed()
        session = ThreadSession()
        self._sessions[key] = session
        return session

    def _evict_if_needed(self) -> None:
        while len(self._sessions) >= self._max_sessions:
            self._sessions.popitem(last=False)

    def mark_active(self, key: str) -> None:
        self.get(key).bot_active = True

    def has_pending_quiz(self, key: str) -> bool:
        return key in self._sessions and self._sessions[key].pending_quiz is not None

    def peek_quiz(self, key: str) -> QuizItem | None:
        if key not in self._sessions:
            return None
        return self._sessions[key].pending_quiz

    def set_quiz(self, key: str, item: QuizItem) -> None:
        session = self.get(key)
        session.pending_quiz = item
        session.bot_active = True

    def clear_quiz(self, key: str) -> QuizItem | None:
        if key not in self._sessions:
            return None
        item = self._sessions[key].pending_quiz
        self._sessions[key].pending_quiz = None
        return item

    def is_bot_active(self, key: str) -> bool:
        return key in self._sessions and self._sessions[key].bot_active

    def append_user(self, key: str, text: str) -> None:
        session = self.get(key)
        session.history.append(ChatTurn(role="user", text=text))
        self._trim_history(session)

    def append_assistant(self, key: str, text: str) -> None:
        session = self.get(key)
        session.history.append(ChatTurn(role="assistant", text=text))
        self._trim_history(session)

    def history_for_prompt(self, key: str) -> list[ChatTurn]:
        if key not in self._sessions:
            return []
        return list(self._sessions[key].history)

    def _trim_history(self, session: ThreadSession) -> None:
        if len(session.history) > self._max_turns:
            session.history = session.history[-self._max_turns :]
