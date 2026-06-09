"""Tests for long quiz body, image blocks, and block limits."""

import pytest

from febot.quiz import QuizItem
from febot.slack_format import MAX_BLOCKS, MAX_SECTION_LEN
from febot.slack_handlers import build_quiz_message


@pytest.fixture(autouse=True)
def _mock_reachable_quiz_images(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "febot.slack_handlers._image_url_reachable",
        lambda url: bool(url) and url.startswith("http"),
    )


def test_build_quiz_message_long_body_chunked() -> None:
    long_body = "説明。" * 800
    item = QuizItem(
        qid="long-1",
        qtype="科目B",
        body=long_body,
        choices="**ア** a\n**イ** b\n**ウ** c\n**エ** d",
        correct="ア",
        explanation="e",
        category="科目B",
    )
    _fallback, blocks = build_quiz_message(item)
    section_texts = [
        b["text"]["text"] for b in blocks if b.get("type") == "section" and "text" in b
    ]
    assert any(len(t) <= MAX_SECTION_LEN for t in section_texts)
    assert len(blocks) <= MAX_BLOCKS


def test_build_quiz_message_with_images() -> None:
    item = QuizItem(
        qid="fig-1",
        qtype="科目A",
        body="図1を参照",
        choices="**ア** a\n**イ** b",
        correct="ア",
        explanation="e",
        category="科目A",
        image_urls=("https://example.com/page-3.png",),
    )
    _fallback, blocks = build_quiz_message(item)
    image_blocks = [b for b in blocks if b.get("type") == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["image_url"] == "https://example.com/page-3.png"
