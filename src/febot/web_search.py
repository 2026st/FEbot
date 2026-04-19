"""Web search fallback using DuckDuckGo (no API key required)."""

from __future__ import annotations

import logging

from openai import OpenAI

log = logging.getLogger(__name__)

SEARCH_SYSTEM_PROMPT = """あなたは基本情報技術者試験（FE）の学習支援ボットです。
以下のWeb検索結果をもとに、ユーザーの質問に日本語で簡潔に答えてください。
情報が不十分な場合はその旨を伝えてください。
回答の末尾に【出典URL】として参照したURLを箇条書きで記載してください。"""


def search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo text search. Returns list of {title, body, href}. Empty list on failure."""
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        log.warning("DuckDuckGo search failed: %s", e)
        return []


def build_answer(oai: OpenAI, model: str, question: str, results: list[dict]) -> tuple[str, str]:
    """Generate answer from web results using LLM.

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

    user_content = f"【質問】\n{question}\n\n【Web検索結果】\n{context}"
    chat = oai.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SEARCH_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
    )
    answer_text = (chat.choices[0].message.content or "").strip()

    urls = "\n".join(f"- {r.get('href', '')}" for r in results if r.get("href"))
    corpus_md = f"# Q: {question}\n\n{answer_text}\n\n## 参照URL\n{urls}\n"

    return answer_text, corpus_md
