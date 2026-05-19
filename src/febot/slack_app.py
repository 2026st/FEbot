"""Slack Bolt app: Socket Mode, mentions, DM, quiz threads, /fe-help."""

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
from febot.quiz import QuizItem, load_quiz_items, normalize_answer, pick_random
from febot.rag import RagEngine
from febot.thread_session import (
    ThreadSessionStore,
    thread_key,
    thread_root_ts_from_event,
)

log = logging.getLogger(__name__)

QUIZ_KEYWORDS = ("過去問", "出題", "練習問題")

_THINKING_MESSAGES = [
    "🤔 thinking...",
    "📚 コーパスをあさり中...",
    "🔍 知識の海を泳いでいます...",
    "⚙️ RAGエンジン起動中...",
    "🧠 基本情報技術者試験ボット、全力稼働中...",
]

NO_AI_REPLY = (
    "RAG（用語解説・生成回答）を使う設定がありません。\n"
    "• Bedrock（チャット）: `BEDROCK_CHAT_MODEL_ID` と AWS 認証に加え、埋め込み用に `AI_API_KEY` を設定し "
    "`python3 scripts/ingest.py` を実行してください。\n"
    "• OpenAI 互換のみ: `USE_BEDROCK=false` にするか Bedrock 用チャット ID を空にし、`AI_API_KEY` を設定して ingest してください。"
)


def _help_text(settings: Settings) -> str:
    base = (
        "*FE 学習ボット（RAG / PoC）*\n\n"
        "• チャンネルでは *@ボット* にメンションして質問（用語・学習の相談など）\n"
        "• DM でも同じように送れます\n"
        "• 「過去問」「出題」「練習問題」と書くと *オリジナル練習問題* を出します（スレッドに解答）\n"
        "• ボットが応答したスレッドでは、追質問をメンションなしで送れます（会話履歴はプロセス稼働中のみ保持）\n"
        "• 回答は登録コーパスに基づく生成です。*誤りや不足があり得ます*。必ず公式教材で確認してください。\n"
        "• コーパスには IPA 公表 PDF から抽出した `ipa-*.md` とオリジナル教材があります。利用上の留意点: https://www.ipa.go.jp/shiken/faq.html#seido\n"
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


def _make_cache_filename(question: str) -> str:
    date = datetime.date.today().isoformat()
    slug = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff]", "_", question[:40]).strip("_")
    return f"web_cache_{date}_{slug}.md"


def _reply_thread_ts(event: dict) -> str:
    """Slack thread parent ts for replies (same as thread_root for new threads)."""
    return thread_root_ts_from_event(event)


def _session_key(event: dict) -> str:
    return thread_key(event["channel"], thread_root_ts_from_event(event))


def _grade_quiz_answer(item: QuizItem, ans: str) -> str:
    if ans == item.correct:
        return f"正解です（{item.correct}）。\n*解説*: {item.explanation}"
    return f"不正解です。あなたの解答: {ans} / 正解: {item.correct}\n*解説*: {item.explanation}"


def _try_handle_quiz_reply(
    state: BotState,
    event: dict,
    text: str,
    say,
) -> bool:
    """Handle quiz answer in thread. Returns True if handled."""
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return False
    key = _session_key(event)
    item = state.sessions.peek_quiz(key)
    if item is None:
        return False

    ans = normalize_answer(text)
    if not ans:
        say("「ア」「イ」「ウ」「エ」で答えてください。", thread_ts=thread_ts)
        return True

    msg = _grade_quiz_answer(item, ans)
    say(msg, thread_ts=thread_ts)
    state.sessions.clear_quiz(key)
    state.sessions.append_user(key, text)
    state.sessions.append_assistant(key, msg)
    return True


def _handle_rag_question(
    rag: RagEngine,
    settings: Settings,
    state: BotState,
    session_key: str,
    text: str,
    user_id: str,
    say,
    thread_ts: str | None = None,
) -> None:
    """RAG → Web search fallback → corpus save → reply."""
    kwargs = {"thread_ts": thread_ts} if thread_ts else {}
    history = state.sessions.history_for_prompt(session_key)
    state.sessions.append_user(session_key, text)
    state.sessions.mark_active(session_key)

    say(random.choice(_THINKING_MESSAGES), **kwargs)

    try:
        out = rag.answer(user_id, text, history=history or None)
    except Exception as e:
        log.exception("rag failed: %s", e)
        msg = slack_reply_for_bedrock_access_error(e)
        err_text = msg or "処理中にエラーが発生しました。管理者に連絡してください。"
        say(err_text, **kwargs)
        state.sessions.append_assistant(session_key, err_text)
        return

    if out is not None:
        reply_text = out.text
        citations = []
        for src in out.sources:
            if src.startswith("web_cache_"):
                try:
                    content = (settings.corpus_dir / src).read_text(encoding="utf-8")
                    for line in content.splitlines():
                        if line.startswith("- http"):
                            url = line.lstrip("- ").strip()
                            if url not in citations:
                                citations.append(url)
                except Exception:
                    pass
            else:
                clean_src = src.split("（")[0] if "（" in src else src
                link = f"https://github.com/2026st/FEbot/blob/main/data/corpus/{clean_src}"
                if link not in citations:
                    citations.append(link)

        if citations:
            reply_text += "\n\n【出典】\n" + "\n".join(f"- {c}" for c in citations)

        say(reply_text, **kwargs)
        state.sessions.append_assistant(session_key, reply_text)
        return

    say("ナレッジベースに情報が見つかりませんでした。Webを検索中です...", **kwargs)
    max_results = int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "5"))
    results = ws.search(text, max_results=max_results)
    if not results:
        fallback = "Web検索でも情報が見つかりませんでした。別のキーワードでお試しください。"
        say(fallback, **kwargs)
        state.sessions.append_assistant(session_key, fallback)
        return

    try:
        slack_text, corpus_md = ws.build_answer(rag.llm, text, results, history=history or None)
    except Exception as e:
        log.exception("web answer build failed: %s", e)
        err_text = "Web検索結果の要約中にエラーが発生しました。"
        say(err_text, **kwargs)
        state.sessions.append_assistant(session_key, err_text)
        return

    try:
        rag.add_to_corpus(corpus_md, _make_cache_filename(text))
    except Exception as e:
        log.warning("corpus save failed (non-fatal): %s", e)

    full_reply = slack_text + "\n\n_（Web検索より取得。次回からはナレッジベースで回答します）_"
    say(full_reply, **kwargs)
    state.sessions.append_assistant(session_key, full_reply)


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
    say(_format_quiz(item), **kwargs)
    key = thread_key(event["channel"], thread_ts or event["ts"])
    state.sessions.set_quiz(key, item)


def _run_rag_if_allowed(
    rag: RagEngine | None,
    content_filter: ContentFilter | None,
    settings: Settings,
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
        settings,
        state,
        _session_key(event),
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
    state = BotState(quiz_items=load_quiz_items(settings.corpus_dir))

    app = App(token=settings.slack_token)

    @app.command("/fe-help")
    def fe_help(ack, respond):
        ack()
        respond(_help_text(settings))

    @app.event("app_mention")
    def on_mention(event, say, logger):
        text = _strip_mentions(event.get("text", ""))
        reply_ts = _reply_thread_ts(event)
        if not text:
            say("メッセージを入力してください。", thread_ts=reply_ts)
            return
        if _wants_quiz(text):
            _post_quiz(state, event, say, thread_ts=reply_ts)
            return
        _run_rag_if_allowed(
            rag,
            content_filter,
            settings,
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

        ch_type = event.get("channel_type")
        thread_ts = event.get("thread_ts")
        text = (event.get("text") or "").strip()

        if thread_ts and _try_handle_quiz_reply(state, event, text, say):
            return

        key = _session_key(event)
        in_thread = bool(thread_ts)
        bot_active = state.sessions.is_bot_active(key)

        if in_thread and bot_active:
            if not text:
                return
            _run_rag_if_allowed(
                rag,
                content_filter,
                settings,
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
            resp = say(_format_quiz(item))
            quiz_root = resp.get("ts") or event["ts"]
            state.sessions.set_quiz(thread_key(event["channel"], quiz_root), item)
            return
        _run_rag_if_allowed(
            rag,
            content_filter,
            settings,
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
        try:
            chromadb.PersistentClient(path=str(settings.chroma_path)).get_collection(COLLECTION)
        except Exception as e:
            log.error(
                "Chroma collection %r not found under %s. Run: python scripts/ingest.py (%s)",
                COLLECTION,
                settings.chroma_path,
                e,
            )
            raise SystemExit(1) from e
    else:
        log.warning(
            "RAG 用の認証が無いため Chroma をスキップします（Slack のみ接続確認モード）。"
            "Bedrock 利用時は AWS 認証に加え埋め込み用の AI_API_KEY が必要。OpenAI 互換のみなら AI_API_KEY を設定し ingest を実行してください。"
        )
    app, _state = create_app(settings)
    handler = SocketModeHandler(app, settings.slack_app_token)
    log.info("FEbot starting (Socket Mode)")
    handler.start()
