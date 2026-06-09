"""Slack thread/quiz handlers (no RAG import — safe for unit tests)."""

from __future__ import annotations

import time
from collections import OrderedDict

from febot.quiz import QuizItem, normalize_quiz_reply, parse_choice_lines
from febot.slack_format import markdown_to_mrkdwn
from febot.thread_session import ThreadSessionStore, thread_key, thread_root_ts_from_event

_PROCESSED_EVENT_TTL_SEC = 5.0
_PROCESSED_EVENT_MAX = 100


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


def format_quiz_history(item: QuizItem) -> str:
    lines = [
        f"【練習問題】`{item.qid}` ({item.qtype})",
        item.body,
        "",
    ]
    for mark, text in parse_choice_lines(item.choices):
        lines.append(f"**{mark}** {text}")
    lines.append("")
    lines.append("（選択肢ボタン付きで出題）")
    return "\n".join(lines)


def build_quiz_message(item: QuizItem) -> tuple[str, list[dict]]:
    """Build Slack Block Kit message with per-choice select buttons."""
    body = markdown_to_mrkdwn(item.body)
    fallback_lines = [
        f"【練習問題】{item.qid} ({item.qtype})",
        body,
        "",
    ]
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"練習問題 {item.qid}",
                "emoji": True,
            },
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": item.qtype}],
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
    ]
    parsed = parse_choice_lines(item.choices)
    for mark, choice_text in parsed:
        choice_mrkdwn = markdown_to_mrkdwn(f"*{mark}* {choice_text}")
        fallback_lines.append(f"{mark}: {choice_text}")
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": choice_mrkdwn},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": mark, "emoji": True},
                    "action_id": "quiz_answer",
                    "value": mark,
                },
            }
        )
    fallback_lines.append("")
    fallback_lines.append("各選択肢のボタンから選ぶか、「ア」〜「エ」で返信してください。")
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "各選択肢の *ボタン* から選ぶか、このスレッドに「ア」〜「エ」で返信できます。",
                }
            ],
        }
    )
    return "\n".join(fallback_lines), blocks


def _quiz_thread_root_from_message(message: dict) -> str:
    return message.get("thread_ts") or message["ts"]


def _finalize_quiz_answer(
    sessions: ThreadSessionStore,
    key: str,
    item: QuizItem,
    ans: str,
    say,
    *,
    thread_ts: str,
) -> None:
    msg = grade_quiz_answer(item, ans)
    say(msg, thread_ts=thread_ts)
    sessions.clear_quiz(key)
    sessions.append_user(key, ans)
    sessions.append_assistant(key, msg)


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

    _finalize_quiz_answer(sessions, key, item, ans, say, thread_ts=thread_ts)
    return True


def handle_quiz_button(
    sessions: ThreadSessionStore,
    body: dict,
    say,
) -> bool:
    """Handle quiz choice button click. Returns True if graded."""
    actions = body.get("actions") or []
    if not actions:
        return False
    ans = actions[0].get("value")
    if ans not in ("ア", "イ", "ウ", "エ"):
        return False

    channel = body["channel"]["id"]
    message = body["message"]
    thread_ts = _quiz_thread_root_from_message(message)
    key = thread_key(channel, thread_ts)
    item = sessions.peek_quiz(key)
    if item is None:
        return False

    _finalize_quiz_answer(sessions, key, item, ans, say, thread_ts=thread_ts)
    return True
