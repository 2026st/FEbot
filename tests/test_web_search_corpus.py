"""Tests for web search corpus markdown and citation URL extraction."""

from febot.web_search import build_corpus_markdown, urls_from_web_cache_content


def test_build_corpus_markdown_includes_question_and_urls() -> None:
    md = build_corpus_markdown(
        "公開鍵暗号とは",
        "公開鍵暗号は…",
        [{"href": "https://example.com/a"}, {"href": "https://example.com/b"}],
    )
    assert "# Q: 公開鍵暗号とは" in md
    assert "公開鍵暗号は…" in md
    assert "- https://example.com/a" in md
    assert "- https://example.com/b" in md


def test_urls_from_web_cache_content() -> None:
    content = "# Q: test\n\nanswer\n\n## 参照URL\n- https://a.example\n- https://b.example\n"
    assert urls_from_web_cache_content(content) == [
        "https://a.example",
        "https://b.example",
    ]
