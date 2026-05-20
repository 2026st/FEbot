"""Slack Bolt app: Socket Mode, mentions, DM, quiz threads, /fe-help."""

from __future__ import annotations

import logging
import os
import random
import re
from dataclasses import dataclass, field

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from febot import web_search as ws
from febot.bedrock_errors import slack_reply_for_bedrock_access_error
from febot.config import Settings
from febot.content_filter import ContentFilter
from febot.quiz import QuizItem, load_quiz_items, pick_random
from febot.rag import RagEngine
from febot.slack_handlers import (
    ProcessedEvents,
    session_key,
    text_mentions_bot,
    try_handle_quiz_reply,
)
from febot.thread_session import ThreadSessionStore, thread_key, thread_root_ts_from_event

log = logging.getLogger(__name__)

QUIZ_KEYWORDS = ("過去問", "出題", "練習問題")

_THINKING_MESSAGES = [
    "🤔 thinking...",
    "🔍 ナレッジベースを検索中...",
    "⚙️ RAGエンジン起動中...",
    "🧠 基本情報技術者試験ボット、全力稼働中...",
]

NO_AI_REPLY = (
    "RAG（用語解説・生成回答）を使う設定がありません。\n"
    "• Bedrock（チャット）: `BEDROCK_CHAT_MODEL_ID` と AWS 認証に加え、埋め込み用に `AI_API_KEY` を設定してください。\n"
    "• OpenAI 互換のみ: `USE_BEDROCK=false` にするか Bedrock 用チャット ID を空にし、`AI_API_KEY` を設定してください。\n"
    "• ベクトル DB（Chroma または Supabase）が投入済みである必要があります。"
)


def _help_text(settings: Settings) -> str:
    base = (
        "*FE 学習ボット（RAG / PoC）*\n\n"
        "• チャンネルでは *@ボット* にメンションして質問（用語・学習の相談など）\n"
        "• DM でも同じように送れます\n"
        "• 「過去問」「出題」「練習問題」と書くと練習問題を出します（データ未設定時はエラー）\n"
        "• ボットが応答したスレッドでは、追質問をメンションなしで送れます（会話履歴はプロセス稼働中のみ保持）\n"
        "• 回答はベクトル DB の参照抜粋または Web 検索に基づく生成です。*誤りや不足があり得ます*。必ず公式教材で確認してください。\n"
    )
    if not settings.rag_enabled():
        return base + (
            "\n*現在の状態*: AI（Bedrock または OpenAI 互換）が利用できないため、用語・質問への生成回答のみオフです。"
            " Slack 連携の確認は可能です。\n"
        )
    return base


@dataclass
class BotState:
    """In-memory bot state (PoC)."""

    sessions: ThreadSessionStore = field(default_factory=ThreadSessionStore)
    quiz_items: list[QuizItem] = field(default_factory=list)
    processed_events: ProcessedEvents = field(default_factory=ProcessedEvents)
    bot_user_id: str | None = None


def _strip_mentions(text: str) -> str:
    return re.sub(r"<@[^>]+>", "", text).strip()


def _wants_quiz(text: str) -> bool:
    return any(k in text for k in QUIZ_KEYWORDS)


def _format_quiz(q: QuizItem) -> str:
    return (
        f"【練習問題】`{q.qid}` ({q.qtype})\n"
        f"{q.body}\n\n"
        f"{q.choices}\n\n"
        "答えはこのスレッドに「ア」「イ」「ウ」「エ」で返信してください。"
    )


def _reply_thread_ts(event: dict) -> str:
    """Slack thread parent ts for replies (same as thread_root for new threads)."""
    return thread_root_ts_from_event(event)


def _mark_event_processed(state: BotState, event: dict) -> None:
    state.processed_events.mark(event["channel"], event["ts"])


def _event_already_processed(state: BotState, event: dict) -> bool:
    return state.processed_events.was_processed(event["channel"], event["ts"])


def _handle_rag_question(
    rag: RagEngine,
    state: BotState,
    session_key_str: str,
    text: str,
    user_id: str,
    say,
    thread_ts: str | None = None,
) -> None:
    """RAG → Web search fallback → reply."""
    kwargs = {"thread_ts": thread_ts} if thread_ts else {}
    history = state.sessions.history_for_prompt(session_key_str)
    state.sessions.append_user(session_key_str, text)
    state.sessions.mark_active(session_key_str)

    say(random.choice(_THINKING_MESSAGES), **kwargs)

    try:
        out = rag.answer(user_id, text, history=history or None)
    except Exception as e:
        log.exception("rag failed: %s", e)
        msg = slack_reply_for_bedrock_access_error(e)
        err_text = msg or "処理中にエラーが発生しました。管理者に連絡してください。"
        say(err_text, **kwargs)
        state.sessions.append_assistant(session_key_str, err_text)
        return

    if out is not None:
        reply_text = out.text
        if out.sources:
            reply_text += "\n\n【参照】\n" + "\n".join(f"- {s}" for s in out.sources)

        say(reply_text, **kwargs)
        state.sessions.append_assistant(session_key_str, reply_text)
        return

    say("ナレッジベースに情報が見つかりませんでした。Webを検索中です...", **kwargs)
    max_results = int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "5"))
    results = ws.search(text, max_results=max_results)
    if not results:
        fallback = "Web検索でも情報が見つかりませんでした。別のキーワードでお試しください。"
        say(fallback, **kwargs)
        state.sessions.append_assistant(session_key_str, fallback)
        return

    try:
        slack_text = ws.build_answer(rag.llm, text, results, history=history or None)
    except Exception as e:
        log.exception("web answer build failed: %s", e)
        err_text = "Web検索結果の要約中にエラーが発生しました。"
        say(err_text, **kwargs)
        state.sessions.append_assistant(session_key_str, err_text)
        return

    full_reply = slack_text + "\n\n_（Web検索より取得）_"
    say(full_reply, **kwargs)
    state.sessions.append_assistant(session_key_str, full_reply)


def _post_quiz(
    state: BotState,
    event: dict,
    say,
    *,
    thread_ts: str | None,
) -> None:
    item = pick_random(state.quiz_items)
    if not item:
        say("練習問題データが見つかりません。", thread_ts=thread_ts)
        return
    kwargs = {"thread_ts": thread_ts} if thread_ts else {}
    quiz_text = _format_quiz(item)
    say(quiz_text, **kwargs)
    key = thread_key(event["channel"], thread_ts or event["ts"])
    state.sessions.set_quiz(key, item)
    state.sessions.append_assistant(key, quiz_text)


def _run_rag_if_allowed(
    rag: RagEngine | None,
    content_filter: ContentFilter | None,
    state: BotState,
    event: dict,
    text: str,
    say,
    *,
    thread_ts: str | None,
    filtered_msg: str,
) -> None:
    if rag is None:
        say(NO_AI_REPLY, thread_ts=thread_ts)
        return
    if content_filter is not None:
        filter_result = content_filter.validate(text)
        if not filter_result.is_valid:
            say(filtered_msg, thread_ts=thread_ts)
            log.info(
                "Question filtered out: %s... Reason: %s",
                text[:100],
                filter_result.reason,
            )
            return
    _handle_rag_question(
        rag,
        state,
        session_key(event),
        text,
        event.get("user", ""),
        say,
        thread_ts=thread_ts,
    )


def create_app(settings: Settings) -> tuple[App, BotState]:
    rag: RagEngine | None = RagEngine(settings) if settings.rag_enabled() else None
    content_filter: ContentFilter | None = (
        ContentFilter(settings) if settings.rag_enabled() else None
    )
    state = BotState(quiz_items=load_quiz_items())

    app = App(token=settings.slack_token)
    try:
        auth = app.client.auth_test()
        state.bot_user_id = auth.get("user_id")
        log.info("Slack bot user_id=%s", state.bot_user_id)
    except Exception as e:
        log.warning("auth.test failed (mention dedupe disabled): %s", e)

    @app.command("/fe-help")
    def fe_help(ack, respond):
        ack()
        respond(_help_text(settings))

    @app.event("app_mention")
    def on_mention(event, say, logger):
        _mark_event_processed(state, event)
        text = _strip_mentions(event.get("text", ""))
        reply_ts = _reply_thread_ts(event)
        if not text:
            say("メッセージを入力してください。", thread_ts=reply_ts)
            return
        if event.get("thread_ts") and try_handle_quiz_reply(state.sessions, event, text, say):
            return
        if _wants_quiz(text):
            _post_quiz(state, event, say, thread_ts=reply_ts)
            return
        _run_rag_if_allowed(
            rag,
            content_filter,
            state,
            event,
            text,
            say,
            thread_ts=reply_ts,
            filtered_msg=(
                "申し訳ございません。\n"
                "その質問は基本情報技術者試験やIT・プログラミングに関連していないと判断されました。\n"
                "※ もし関連がある場合は、文脈を明確にしてください。"
            ),
        )

    @app.event("message")
    def on_message(event, say, logger):
        if event.get("bot_id") or event.get("subtype") in (
            "bot_message",
            "message_changed",
            "message_deleted",
            "channel_join",
            "channel_leave",
        ):
            return

        if _event_already_processed(state, event):
            return

        ch_type = event.get("channel_type")
        thread_ts = event.get("thread_ts")
        text = (event.get("text") or "").strip()

        if text_mentions_bot(text, state.bot_user_id):
            return

        if thread_ts and try_handle_quiz_reply(state.sessions, event, text, say):
            _mark_event_processed(state, event)
            return

        key = session_key(event)
        in_thread = bool(thread_ts)
        bot_active = state.sessions.is_bot_active(key)

        if in_thread and bot_active:
            if not text:
                return
            _run_rag_if_allowed(
                rag,
                content_filter,
                state,
                event,
                text,
                say,
                thread_ts=thread_ts,
                filtered_msg=(
                    "申し訳ございませんが、その質問は基本情報技術者試験や"
                    "IT・プログラミングに関連していないため、回答できません。"
                ),
            )
            return

        if ch_type != "im":
            return

        if not text:
            return
        if _wants_quiz(text):
            item = pick_random(state.quiz_items)
            if not item:
                say("練習問題データが見つかりません。")
                return
            quiz_text = _format_quiz(item)
            resp = say(quiz_text)
            quiz_root = resp.get("ts") or event["ts"]
            dm_key = thread_key(event["channel"], quiz_root)
            state.sessions.set_quiz(dm_key, item)
            state.sessions.append_assistant(dm_key, quiz_text)
            return
        _run_rag_if_allowed(
            rag,
            content_filter,
            state,
            event,
            text,
            say,
            thread_ts=None,
            filtered_msg=(
                "申し訳ございませんが、その質問は基本情報技術者試験や"
                "IT・プログラミングに関連していないため、回答できません。"
            ),
        )

    return app, state


def run() -> None:
    import chromadb

    from febot.rag import COLLECTION

    logging.basicConfig(level=logging.INFO)
    settings = Settings.load()
    if settings.rag_enabled():
        if settings.use_supabase:
            log.info("Using Supabase for vector search (Chroma startup check skipped)")
        else:
            try:
                chromadb.PersistentClient(path=str(settings.chroma_path)).get_collection(COLLECTION)
            except Exception as e:
                log.error(
                    "Chroma collection %r not found under %s. "
                    "Ensure vector data exists at CHROMA_PATH (%s)",
                    COLLECTION,
                    settings.chroma_path,
                    e,
                )
                raise SystemExit(1) from e
    else:
        log.warning(
            "RAG 用の認証が無いためベクトル DB チェックをスキップします（Slack のみ接続確認モード）。"
            "Bedrock 利用時は AWS 認証に加え埋め込み用の AI_API_KEY が必要。"
            "OpenAI 互換のみなら AI_API_KEY を設定し、ベクトル DB を用意してください。"
        )
    app, _state = create_app(settings)
    handler = SocketModeHandler(app, settings.slack_app_token)
    log.info("FEbot starting (Socket Mode)")
    handler.start()
