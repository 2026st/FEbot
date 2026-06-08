"""Web search fallback using DuckDuckGo (no API key required)."""

from __future__ import annotations

import logging

from febot.llm_backend import ChatEmbedBackend
from febot.slack_format import SLACK_OUTPUT_RULES
from febot.thread_session import ChatTurn, build_user_content_with_history

log = logging.getLogger(__name__)

SEARCH_SYSTEM_PROMPT = (
    """あなたは基本情報技術者試験（FE）の学習支援ボットです。
以下のWeb検索結果をもとに、ユーザーの質問に日本語で初学者でも分かるように丁寧に答えてください。
情報が不十分な場合はその旨を伝えてください。
回答の末尾に【出典URL】として参照したURLを箇条書きで記載してください。ただし、出典URLがない場合は記載しないでください。

"""
    + SLACK_OUTPUT_RULES
)


def search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo text search. Returns list of {title, body, href}. Empty list on failure."""
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        log.warning("DuckDuckGo search failed: %s", e)
        return []


def build_answer(
    llm: ChatEmbedBackend,
    question: str,
    results: list[dict],
    *,
    history: list[ChatTurn] | None = None,
) -> tuple[str, str]:
    """Generate answer from web results using the configured LLM backend.

    Returns:
        (slack_reply_text, corpus_markdown_to_save)
    """
    context_parts = []
    for r in results:
        title = r.get("title", "")
        url = r.get("href", "")
        body = r.get("body", "")[:500]
        context_parts.append(f"タイトル: {title}\nURL: {url}\n内容: {body}")
    context = "\n\n---\n\n".join(context_parts)

    user_content = build_user_content_with_history(
        question=question,
        context=context,
        history=history,
        question_heading="【質問】",
        context_heading="【Web検索結果】",
    )
    answer_text = llm.chat(
        SEARCH_SYSTEM_PROMPT,
        user_content,
        temperature=0.3,
        max_tokens=None,
    )

    urls = "\n".join(f"- {r.get('href', '')}" for r in results if r.get("href"))
    corpus_md = f"# Q: {question}\n\n{answer_text}\n\n## 参照URL\n{urls}\n"

    return answer_text, corpus_md
