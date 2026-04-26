"""Slack Bolt app: Socket Mode, mentions, DM, quiz threads, /fe-help."""

from __future__ import annotations

import datetime
import logging
import os
import re
from dataclasses import dataclass, field

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from febot import web_search as ws
from febot.config import Settings
from febot.quiz import QuizItem, load_quiz_items, normalize_answer, pick_random
from febot.rag import RagEngine

log = logging.getLogger(__name__)

QUIZ_KEYWORDS = ("過去問", "出題", "練習問題")

NO_AI_REPLY = (
    "`AI_API_KEY` が設定されていないため、RAG（用語解説・生成回答）は利用できません。\n"
    "Slack との接続は問題ありません。`.env` に `AI_API_KEY` を設定し、`python3 scripts/ingest.py` のあとで RAG を有効にしてください。"
)


def _help_text(settings: Settings) -> str:
    base = (
        "*FE 学習ボット（RAG / PoC）*\n\n"
        "• チャンネルでは *@ボット* にメンションして質問（用語・学習の相談など）\n"
        "• DM でも同じように送れます\n"
        "• 「過去問」「出題」「練習問題」と書くと *オリジナル練習問題* を出します（スレッドに解答）\n"
        "• 回答は登録コーパスに基づく生成です。*誤りや不足があり得ます*。必ず公式教材で確認してください。\n"
        "• コーパスには IPA 公表 PDF から抽出した `ipa-*.md` とオリジナル教材があります。利用上の留意点: https://www.ipa.go.jp/shiken/faq.html#seido\n"
    )
    if not settings.rag_enabled():
        return base + (
            "\n*現在の状態*: `AI_API_KEY` 未設定のため、用語・質問への生成回答のみオフです。"
            " Slack 連携の確認は可能です。\n"
        )
    return base


@dataclass
class BotState:
    """In-memory quiz state (PoC). Key = Slack ts of bot's quiz message."""

    pending_quiz: dict[str, QuizItem] = field(default_factory=dict)
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


def _handle_rag_question(
    rag: RagEngine,
    settings: Settings,
    text: str,
    user_id: str,
    say,
    thread_ts: str | None = None,
) -> None:
    """RAG → Web search fallback → corpus save → reply."""
    kwargs = {"thread_ts": thread_ts} if thread_ts else {}

    try:
        out = rag.answer(user_id, text)
    except Exception as e:
        log.exception("rag failed: %s", e)
        say("処理中にエラーが発生しました。管理者に連絡してください。", **kwargs)
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
                # Handle 'glossary.md（用語マッチ）' or normal files
                clean_src = src.split("（")[0] if "（" in src else src
                link = f"https://github.com/2026st/FEbot/blob/main/data/corpus/{clean_src}"
                if link not in citations:
                    citations.append(link)

        if citations:
            reply_text += "\n\n【出典】\n" + "\n".join(f"- {c}" for c in citations)

        say(reply_text, **kwargs)
        return

    # No knowledge in corpus → web search fallback
    say("ナレッジベースに情報が見つかりませんでした。Webを検索中です...", **kwargs)
    max_results = int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "5"))
    results = ws.search(text, max_results=max_results)
    if not results:
        say(
            "Web検索でも情報が見つかりませんでした。別のキーワードでお試しください。",
            **kwargs,
        )
        return

    try:
        slack_text, corpus_md = ws.build_answer(rag._oai, settings.ai_chat_model, text, results)
    except Exception as e:
        log.exception("web answer build failed: %s", e)
        say("Web検索結果の要約中にエラーが発生しました。", **kwargs)
        return

    try:
        rag.add_to_corpus(corpus_md, _make_cache_filename(text))
    except Exception as e:
        log.warning("corpus save failed (non-fatal): %s", e)

    say(
        slack_text + "\n\n_（Web検索より取得。次回からはナレッジベースで回答します）_",
        **kwargs,
    )


def create_app(settings: Settings) -> tuple[App, BotState]:
    rag: RagEngine | None = RagEngine(settings) if settings.rag_enabled() else None
    state = BotState(quiz_items=load_quiz_items(settings.corpus_dir))

    app = App(token=settings.slack_token)

    @app.command("/fe-help")
    def fe_help(ack, respond):
        ack()
        respond(_help_text(settings))

    @app.event("app_mention")
    def on_mention(event, say, logger):
        text = _strip_mentions(event.get("text", ""))
        if not text:
            say(
                "メッセージを入力してください。",
                thread_ts=event.get("thread_ts", event["ts"]),
            )
            return
        if _wants_quiz(text):
            item = pick_random(state.quiz_items)
            if not item:
                say(
                    "練習問題データが見つかりません。",
                    thread_ts=event.get("thread_ts", event["ts"]),
                )
                return
            resp = say(_format_quiz(item), thread_ts=event.get("thread_ts", event["ts"]))
            ts = resp.get("ts")
            if ts:
                state.pending_quiz[ts] = item
            return
        if rag is None:
            say(NO_AI_REPLY, thread_ts=event.get("thread_ts", event["ts"]))
            return
        _handle_rag_question(
            rag,
            settings,
            text,
            event.get("user", ""),
            say,
            thread_ts=event.get("thread_ts", event["ts"]),
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

        if thread_ts and thread_ts in state.pending_quiz:
            item = state.pending_quiz[thread_ts]
            raw = event.get("text", "")
            ans = normalize_answer(raw)
            if not ans:
                say("「ア」「イ」「ウ」「エ」で答えてください。", thread_ts=thread_ts)
                return
            if ans == item.correct:
                msg = f"正解です（{item.correct}）。\n*解説*: {item.explanation}"
            else:
                msg = f"不正解です。あなたの解答: {ans} / 正解: {item.correct}\n*解説*: {item.explanation}"
            say(msg, thread_ts=thread_ts)
            del state.pending_quiz[thread_ts]
            return

        if ch_type != "im":
            return

        text = (event.get("text") or "").strip()
        if not text:
            return
        user = event.get("user", "")
        if _wants_quiz(text):
            item = pick_random(state.quiz_items)
            if not item:
                say("練習問題データが見つかりません。")
                return
            resp = say(_format_quiz(item))
            ts = resp.get("ts")
            if ts:
                state.pending_quiz[ts] = item
            return
        if rag is None:
            say(NO_AI_REPLY)
            return
        _handle_rag_question(rag, settings, text, user, say)

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
            "AI_API_KEY 未設定のため Chroma をスキップします（Slack のみ接続確認モード）。RAG を使う場合はキー設定後 ingest を実行してください。"
        )
    app, _state = create_app(settings)
    handler = SocketModeHandler(app, settings.slack_app_token)
    log.info("FEbot starting (Socket Mode)")
    handler.start()
