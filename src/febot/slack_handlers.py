"""Slack thread/quiz handlers (no RAG import — safe for unit tests)."""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from functools import lru_cache

from febot.quiz import (
    KNOWN_CATEGORIES,
    KNOWN_FIELDS,
    QuizItem,
    normalize_quiz_reply,
    parse_choice_lines,
    strip_quiz_common_spec,
)
from febot.slack_format import (
    MAX_BLOCKS,
    _split_mrkdwn_chunks,
    build_slack_blocks,
    markdown_to_mrkdwn,
)
from febot.thread_session import ThreadSessionStore, thread_key, thread_root_ts_from_event

_PROCESSED_EVENT_TTL_SEC = 5.0
_PROCESSED_EVENT_MAX = 100
_FE_QUIZ_CMD_RE = re.compile(r"^/fe-quiz(?:\s+(.*))?\s*$", re.IGNORECASE)
_COMPACT_CHOICE_THRESHOLD = 6


def _quiz_action_id(mark: str) -> str:
    """Unique Slack action_id per choice (required within a Block Kit message)."""
    return f"quiz_answer_{mark}"


@lru_cache(maxsize=512)
def _image_url_reachable(url: str) -> bool:
    """Return True if Slack can fetch the image (HTTP 200, image/*)."""
    if not url:
        return False
    try:
        import httpx

        resp = httpx.get(url, follow_redirects=True, timeout=15.0)
        content_type = resp.headers.get("content-type", "")
        return resp.status_code == 200 and content_type.startswith("image/")
    except Exception:
        return False


def _valid_image_urls(urls: tuple[str, ...]) -> tuple[str, ...]:
    """Drop Storage URLs that are missing or not image/* (Slack rejects them)."""
    return tuple(u for u in urls if u and _image_url_reachable(u))


def parse_fe_quiz_command(text: str) -> str | None:
    """Return filter option when *text* is a ``/fe-quiz`` command, else ``None``."""
    m = _FE_QUIZ_CMD_RE.match(text.strip())
    if not m:
        return None
    return (m.group(1) or "").strip()


def quiz_filter_miss_message(option: str) -> str:
    fields_hint = "、".join(KNOWN_FIELDS)
    cats_hint = "、".join(KNOWN_CATEGORIES)
    return (
        f"「{option}」に一致する問題が見つかりませんでした。\n"
        f"*カテゴリ指定*: {cats_hint}\n"
        f"*分野指定*: {fields_hint}"
    )


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


def _kamoku_b_image_body(item: QuizItem, image_urls: tuple[str, ...]) -> bool:
    """科目B with page PNGs: show images instead of text body."""
    return item.category == "科目B" and bool(image_urls)


def _quiz_display_body(item: QuizItem, image_urls: tuple[str, ...]) -> str:
    if _kamoku_b_image_body(item, image_urls):
        return "（問題文は画像を参照してください）"
    if item.category == "科目B" and item.image_urls and not image_urls:
        if item.source_url:
            return f"（問題文画像を取得できませんでした。<{item.source_url}|公式PDF>を参照してください）"
        return "（問題文画像を取得できませんでした）"
    return strip_quiz_common_spec(item.body)


def format_quiz_history(item: QuizItem) -> str:
    body_line = _quiz_display_body(item)
    lines = [
        f"【練習問題】`{item.qid}` ({item.qtype})",
        body_line,
        "",
    ]
    for mark, text in parse_choice_lines(item.choices):
        lines.append(f"**{mark}** {text}")
    lines.append("")
    lines.append("（選択肢ボタン付きで出題）")
    return "\n".join(lines)


def _quiz_header_title(item: QuizItem) -> str:
    if item.category:
        return f"{item.category} 練習問題"
    return "練習問題"


def _quiz_meta_line(item: QuizItem) -> str:
    parts = [f"`{item.qid}`"]
    if item.field:
        parts.append(item.field)
    if item.qtype:
        parts.append(item.qtype)
    if item.source_url:
        parts.append(f"<{item.source_url}|公式PDF>")
    return " · ".join(parts)


def _choice_section_with_button(mark: str, choice_text: str) -> dict:
    """One choice per section; answer button on the right."""
    choice_mrkdwn = markdown_to_mrkdwn(choice_text)
    text = f"*{mark}*  {choice_mrkdwn}"
    if len(text) > 3000:
        text = text[:2997] + "..."
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": mark, "emoji": True},
            "action_id": _quiz_action_id(mark),
            "value": mark,
        },
    }


def _choices_list_section(parsed: list[tuple[str, str]]) -> dict:
    lines = []
    for mark, text in parsed:
        lines.append(f"*{mark}*  {markdown_to_mrkdwn(text)}")
    body = "\n".join(lines)
    if len(body) > 3000:
        body = body[:2997] + "..."
    return {"type": "section", "text": {"type": "mrkdwn", "text": body}}


def _choice_action_blocks(parsed: list[tuple[str, str]]) -> list[dict]:
    """Group answer buttons into actions blocks (max 5 buttons each)."""
    blocks: list[dict] = []
    buttons: list[dict] = []
    for mark, _ in parsed:
        buttons.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": mark, "emoji": True},
                "action_id": _quiz_action_id(mark),
                "value": mark,
            }
        )
        if len(buttons) == 5:
            blocks.append({"type": "actions", "elements": buttons})
            buttons = []
    if buttons:
        blocks.append({"type": "actions", "elements": buttons})
    return blocks


def _quiz_answer_method_block(marks: tuple[str, ...]) -> dict:
    if len(marks) <= 5:
        range_text = f"*{marks[0]}〜{marks[-1]}*"
    else:
        range_text = f"*{marks[0]}〜{marks[-1]}*（{len(marks)}択）"
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*回答方法*\n各選択肢のボタン（{range_text}）を押してください。",
        },
    }


def _image_blocks(urls: tuple[str, ...], *, alt_prefix: str = "問題図表") -> list[dict]:
    blocks: list[dict] = []
    for i, url in enumerate(urls):
        if not url:
            continue
        blocks.append(
            {
                "type": "image",
                "image_url": url,
                "alt_text": f"{alt_prefix} {i + 1}",
            }
        )
    return blocks


def _quiz_problem_blocks(item: QuizItem, image_urls: tuple[str, ...]) -> list[dict]:
    """Problem statement blocks: PNG for 科目B; text + optional PNG for 科目A."""
    if _kamoku_b_image_body(item, image_urls):
        return _image_blocks(image_urls, alt_prefix="問題文")
    blocks: list[dict] = []
    if item.body.strip():
        blocks.extend(_body_blocks(item, image_urls))
    if image_urls:
        if item.category == "科目A":
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "_図表・表組み・特殊記号は下の画像を参照してください_",
                        }
                    ],
                }
            )
        blocks.extend(_image_blocks(image_urls, alt_prefix="問題・図表"))
    elif not blocks:
        blocks.extend(_body_blocks(item, image_urls))
    return blocks


def _body_blocks(
    item: QuizItem, image_urls: tuple[str, ...], *, compact: bool = False
) -> list[dict]:
    body = _quiz_display_body(item, image_urls)
    if compact:
        mrkdwn = markdown_to_mrkdwn(body)
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": chunk}}
            for chunk in _split_mrkdwn_chunks(mrkdwn)
        ]
    body_fallback, body_blocks = build_slack_blocks(body)
    if not body_blocks:
        mrkdwn = markdown_to_mrkdwn(body)
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": chunk}}
            for chunk in _split_mrkdwn_chunks(mrkdwn)
        ]
    return body_blocks


def build_quiz_message(item: QuizItem) -> tuple[str, list[dict]]:
    """Build Slack Block Kit message: formatted body, choices, answer buttons, images."""
    image_urls = _valid_image_urls(item.image_urls)
    header = _quiz_header_title(item)
    meta = _quiz_meta_line(item)
    parsed = parse_choice_lines(item.choices)
    marks = item.choice_marks

    display_body = _quiz_display_body(item, image_urls)
    fallback_lines = [f"【{header}】{meta}", display_body, ""]
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header, "emoji": True},
        },
        {"type": "context", "elements": [{"type": "mrkdwn", "text": meta}]},
        {"type": "divider"},
        *_quiz_problem_blocks(item, image_urls),
    ]

    if parsed:
        blocks.append({"type": "divider"})
        blocks.append(_quiz_answer_method_block(marks))
        use_compact_choices = len(parsed) >= _COMPACT_CHOICE_THRESHOLD

        if use_compact_choices:
            blocks.append(_choices_list_section(parsed))
            blocks.extend(_choice_action_blocks(parsed))
            for mark, text in parsed:
                fallback_lines.append(f"{mark}: {text}")
        else:
            for mark, choice_text in parsed:
                fallback_lines.append(f"{mark}: {choice_text}")
                blocks.append(_choice_section_with_button(mark, choice_text))

    fallback_lines.append("")
    fallback_lines.append("各選択肢のボタンを押して回答してください。")

    if len(blocks) > MAX_BLOCKS:
        return _build_quiz_message_compact(item, image_urls)

    return "\n".join(fallback_lines), blocks


def _build_quiz_message_compact(
    item: QuizItem, image_urls: tuple[str, ...]
) -> tuple[str, list[dict]]:
    """Fallback when block count exceeds Slack limit."""
    header = _quiz_header_title(item)
    meta = _quiz_meta_line(item)
    parsed = parse_choice_lines(item.choices)
    marks = item.choice_marks

    display_body = _quiz_display_body(item, image_urls)
    fallback_lines = [f"【{header}】{meta}", display_body, ""]
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header, "emoji": True},
        },
        {"type": "context", "elements": [{"type": "mrkdwn", "text": meta}]},
    ]
    if _kamoku_b_image_body(item, image_urls):
        blocks.extend(_image_blocks(image_urls, alt_prefix="問題文"))
    else:
        if item.body.strip():
            blocks.extend(_body_blocks(item, image_urls, compact=True))
        if image_urls:
            if item.category == "科目A":
                blocks.append(
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "_図表・表組み・特殊記号は下の画像を参照してください_",
                            }
                        ],
                    }
                )
            blocks.extend(_image_blocks(image_urls, alt_prefix="問題・図表"))
        elif not blocks:
            blocks.extend(_body_blocks(item, image_urls, compact=True))

    if parsed:
        blocks.append(_quiz_answer_method_block(marks))
        blocks.append(_choices_list_section(parsed))
        blocks.extend(_choice_action_blocks(parsed))
        for mark, choice_text in parsed:
            fallback_lines.append(f"{mark}: {choice_text}")

    fallback_lines.append("")
    fallback_lines.append("各選択肢のボタンを押して回答してください。")
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

    ans = normalize_quiz_reply(text, allowed_marks=item.choice_marks)
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

    channel = body["channel"]["id"]
    message = body["message"]
    thread_ts = _quiz_thread_root_from_message(message)
    key = thread_key(channel, thread_ts)
    item = sessions.peek_quiz(key)
    if item is None:
        return False

    if ans not in item.choice_marks:
        return False

    _finalize_quiz_answer(sessions, key, item, ans, say, thread_ts=thread_ts)
    return True
