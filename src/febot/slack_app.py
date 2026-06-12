"""Slack Bolt app: Socket Mode, mentions, DM, quiz threads, message slash commands."""

from __future__ import annotations

import datetime
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
from febot.easter_eggs import EasterEggHandler, handle_mbti_action
from febot.quiz import (
    QuizItem,
    load_quiz_items_from_supabase,
    pick_filtered,
    pick_random,
)
from febot.rag import RagEngine
from febot.slack_format import (
    FORMAT_TEST_FOOTER,
    build_slack_blocks,
    format_reply_for_history,
    format_test_sample_body,
    wants_format_test,
)
from febot.slack_handlers import (
    ProcessedEvents,
    build_quiz_message,
    format_quiz_history,
    handle_quiz_button,
    is_tips_message,
    quiz_filter_miss_message,
    session_key,
    text_mentions_bot,
    try_handle_quiz_reply,
    try_handle_slash_command,
)
from febot.supabase_quiz import SupabaseQuizStore
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
        "• 「過去問」「出題」「練習問題」と書くと *IPA公式過去問* を出します（多肢対応・図表付き・選択肢ボタン）\n"
        "• ボットが応答したスレッドでは、追質問をメンションなしで送れます（会話履歴はプロセス稼働中のみ保持）\n"
        "• ヘルプ: チャンネルでは `@ボット /fe-help`、スレッド内・DM では `/fe-help`\n"
        "• 回答は登録コーパスに基づく生成です。*誤りや不足があり得ます*。必ず公式教材で確認してください。\n"
        "• 過去問は IPA 公表 PDF 由来（Supabase 保存）。利用上の留意点: https://www.ipa.go.jp/shiken/faq.html#seido\n"
        "\n*コマンド*（チャンネルは @ボット と併用、スレッド内・DM は `/` のみ）\n"
        "• `/fe-help` — このヘルプ\n"
        "• `/fe-quiz` — 全問からランダム出題\n"
        "• `/fe-quiz 科目A` または `/fe-quiz a` — 科目A（知識問題）から出題\n"
        "• `/fe-quiz 科目B` または `/fe-quiz b` — 科目B（アルゴリズム）から出題\n"
        "• `/fe-quiz ネットワーク` など — 分野名で絞り込み出題\n"
        "  （分野例: OS、ネットワーク、データベース、セキュリティ、アルゴリズム、表計算）\n"
        "• `/fe-format-test` または `フォーマットテスト` / `表示テスト`（AI 不要・表示確認）\n"
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


def _make_cache_filename(question: str) -> str:
    date = datetime.date.today().isoformat()
    slug = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff]", "_", question[:40]).strip("_")
    return f"web_cache_{date}_{slug}.md"


def _reply_thread_ts(event: dict) -> str:
    """Slack thread parent ts for replies (same as thread_root for new threads)."""
    return thread_root_ts_from_event(event)


def _mark_event_processed(state: BotState, event: dict) -> None:
    state.processed_events.mark(event["channel"], event["ts"])


def _event_already_processed(state: BotState, event: dict) -> bool:
    return state.processed_events.was_processed(event["channel"], event["ts"])


def _post_format_test(say, **kwargs) -> None:
    """Post fixed sample via Block Kit (same path as RAG answers)."""
    _say_formatted(say, format_test_sample_body(), footer=FORMAT_TEST_FOOTER, **kwargs)


def _try_slash_commands(
    state: BotState,
    event: dict,
    text: str,
    say,
    thread_ts: str | None,
    settings: Settings,
) -> bool:
    kwargs = {"thread_ts": thread_ts} if thread_ts else {}

    def handle_quiz(args: str) -> None:
        _post_quiz(state, event, say, thread_ts=thread_ts, option=args)

    def handle_format_test() -> None:
        _post_format_test(say, **kwargs)

    return try_handle_slash_command(
        text,
        help_text=_help_text(settings),
        say=say,
        handle_quiz=handle_quiz,
        handle_format_test=handle_format_test,
        thread_ts=thread_ts,
    )


def _say_formatted(
    say,
    body: str,
    *,
    sources: list[str] | None = None,
    footer: str | None = None,
    **kwargs,
) -> str:
    """Post RAG answer with Slack Block Kit + mrkdwn; returns text stored in session."""
    fallback, blocks = build_slack_blocks(body, footer=footer, sources=sources)
    history_text = format_reply_for_history(body, sources=sources, footer=footer)
    if blocks:
        say(fallback, blocks=blocks, **kwargs)
    else:
        say(fallback, **kwargs)
    return history_text


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
        citations = []
        for src in out.sources:
            if src.startswith("web_cache_"):
                for url in rag.citation_urls_for_source(src):
                    if url not in citations:
                        citations.append(url)
            else:
                clean_src = src.split("（")[0] if "（" in src else src
                link = f"https://github.com/2026st/FEbot/blob/main/data/corpus/{clean_src}"
                if link not in citations:
                    citations.append(link)

        history_text = _say_formatted(
            say,
            reply_text,
            sources=citations or None,
            **kwargs,
        )
        state.sessions.append_assistant(session_key_str, history_text)
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
        slack_text, corpus_md = ws.build_answer(rag.llm, text, results, history=history or None)
    except Exception as e:
        log.exception("web answer build failed: %s", e)
        err_text = "Web検索結果の要約中にエラーが発生しました。"
        say(err_text, **kwargs)
        state.sessions.append_assistant(session_key_str, err_text)
        return

    try:
        rag.add_to_corpus(corpus_md, _make_cache_filename(text))
    except Exception as e:
        log.warning("corpus save failed (non-fatal): %s", e)

    web_footer = "_（Web検索より取得。次回からはナレッジベースで回答します）_"
    history_text = _say_formatted(
        say,
        slack_text,
        footer=web_footer,
        **kwargs,
    )
    state.sessions.append_assistant(session_key_str, history_text)


def _post_quiz(
    state: BotState,
    event: dict,
    say,
    *,
    thread_ts: str | None,
    option: str = "",
) -> None:
    item = pick_filtered(state.quiz_items, option) if option else pick_random(state.quiz_items)
    if not item:
        msg = quiz_filter_miss_message(option) if option else "練習問題データが見つかりません。"
        say(msg, thread_ts=thread_ts)
        return
    kwargs = {"thread_ts": thread_ts} if thread_ts else {}
    fallback, blocks = build_quiz_message(item)
    resp = say(fallback, blocks=blocks, **kwargs)
    root = thread_ts or resp.get("ts") or event["ts"]
    key = thread_key(event["channel"], root)
    state.sessions.set_quiz(key, item)
    state.sessions.append_assistant(key, format_quiz_history(item))


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


def _load_quiz_for_bot(settings: Settings) -> list[QuizItem]:
    """Load quiz items from Supabase (required for /fe-quiz)."""
    if not settings.use_supabase:
        raise RuntimeError(
            "練習問題出題には SUPABASE_URL と SUPABASE_KEY が必要です。"
            "Supabase に ingest 後、ボットを再起動してください。"
        )
    store = SupabaseQuizStore(settings.supabase_url, settings.supabase_key)
    items = load_quiz_items_from_supabase(store)
    if not items:
        raise RuntimeError(
            "Supabase に練習問題がありません。"
            "python scripts/ipa_ingest_quiz.py ingest --all を実行してください。"
        )
    log.info("Loaded %d quiz items from Supabase", len(items))
    return items


def create_app(settings: Settings) -> tuple[App, BotState]:
    rag: RagEngine | None = RagEngine(settings) if settings.rag_enabled() else None
    content_filter: ContentFilter | None = (
        ContentFilter(settings) if settings.rag_enabled() else None
    )
    state = BotState(quiz_items=_load_quiz_for_bot(settings))
    easter_eggs = EasterEggHandler()

    app = App(token=settings.slack_token)
    try:
        auth = app.client.auth_test()
        state.bot_user_id = auth.get("user_id")
        log.info("Slack bot user_id=%s", state.bot_user_id)
    except Exception as e:
        log.warning("auth.test failed (mention dedupe disabled): %s", e)

    @app.action({"action_id": re.compile(r"^quiz_answer_")})
    def on_quiz_answer(ack, body, say):
        ack()
        handle_quiz_button(state.sessions, body, say)

    @app.action({"action_id": re.compile(r"^mbti_")})
    def on_mbti_action(ack, body, client):
        ack()
        handle_mbti_action(body["actions"][0]["action_id"], body, client)

    @app.event("app_mention")
    def on_mention(event, say, logger):
        _mark_event_processed(state, event)
        text = _strip_mentions(event.get("text", ""))
        reply_ts = _reply_thread_ts(event)
        if not text:
            say("メッセージを入力してください。", thread_ts=reply_ts)
            return
        if _try_slash_commands(state, event, text, say, reply_ts, settings):
            return
        if event.get("thread_ts") and try_handle_quiz_reply(state.sessions, event, text, say):
            return
        if wants_format_test(text):
            _post_format_test(say, thread_ts=reply_ts)
            return
        if _wants_quiz(text):
            _post_quiz(state, event, say, thread_ts=reply_ts)
            return
        if easter_eggs.try_handle(text, say, thread_ts=reply_ts):
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

        if thread_ts and is_tips_message(text):
            _mark_event_processed(state, event)
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
            if _try_slash_commands(state, event, text, say, thread_ts, settings):
                _mark_event_processed(state, event)
                return
            if wants_format_test(text):
                _post_format_test(say, thread_ts=thread_ts)
                _mark_event_processed(state, event)
                return
            if _wants_quiz(text):
                _post_quiz(state, event, say, thread_ts=thread_ts)
                _mark_event_processed(state, event)
                return
            if easter_eggs.try_handle(text, say, thread_ts=thread_ts):
                _mark_event_processed(state, event)
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
        if _try_slash_commands(state, event, text, say, None, settings):
            return
        if wants_format_test(text):
            _post_format_test(say)
            return
        if _wants_quiz(text):
            _post_quiz(state, event, say, thread_ts=None)
            return
        if easter_eggs.try_handle(text, say, thread_ts=None):
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
