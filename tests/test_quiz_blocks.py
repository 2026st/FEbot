"""Tests for quiz Block Kit message and button handling."""

import pytest

from febot.quiz import QuizItem, parse_choice_lines
from febot.slack_handlers import _valid_image_urls, build_quiz_message, handle_quiz_button
from febot.thread_session import ThreadSessionStore, thread_key


@pytest.fixture(autouse=True)
def _mock_reachable_quiz_images(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "febot.slack_handlers._image_url_reachable",
        lambda url: bool(url) and url.startswith("http"),
    )


def test_parse_choice_lines() -> None:
    choices = "**ア** 選択肢A\n**イ** 選択肢B\n**ウ** 選択肢C\n**エ** 選択肢D"
    assert parse_choice_lines(choices) == [
        ("ア", "選択肢A"),
        ("イ", "選択肢B"),
        ("ウ", "選択肢C"),
        ("エ", "選択肢D"),
    ]


def test_build_quiz_message_has_choice_buttons() -> None:
    item = QuizItem(
        qid="q1",
        qtype="午前（擬似）",
        body="問題文です。",
        choices="**ア** A\n**イ** B\n**ウ** C\n**エ** D",
        correct="イ",
        explanation="解説",
    )
    fallback, blocks = build_quiz_message(item)
    assert "問題文" in fallback
    assert blocks[0]["type"] == "header"
    assert blocks[0]["text"]["text"] == "練習問題"
    assert any(b.get("type") == "divider" for b in blocks)
    assert any(
        b.get("type") == "section" and "回答方法" in b.get("text", {}).get("text", "")
        for b in blocks
    )
    choice_sections = [b for b in blocks if b.get("type") == "section" and "accessory" in b]
    assert len(choice_sections) == 4
    assert choice_sections[0]["accessory"]["action_id"] == "quiz_answer_ア"
    assert choice_sections[0]["accessory"]["value"] == "ア"


def test_build_quiz_message_compact_choices_have_unique_action_ids() -> None:
    marks = ["ア", "イ", "ウ", "エ", "オ", "カ"]
    choices = "\n".join(f"**{m}** choice {m}" for m in marks)
    item = QuizItem(
        qid="b-multi",
        qtype="科目B",
        body="長文問題",
        choices=choices,
        correct="ア",
        explanation="e",
        category="科目B",
    )
    _fallback, blocks = build_quiz_message(item)
    action_ids = []
    for block in blocks:
        if block.get("type") == "actions":
            for el in block.get("elements") or []:
                action_ids.append(el["action_id"])
    assert len(action_ids) == len(marks)
    assert len(action_ids) == len(set(action_ids))
    assert all(aid.startswith("quiz_answer_") for aid in action_ids)


def test_build_quiz_message_strips_common_spec_section() -> None:
    appendix = "if (条件)\n  処理\nendif"
    item = QuizItem(
        qid="ipa-b-q01",
        qtype="科目B（IPA 2023r05）",
        body=f"次のプログラムの出力はどれか。\n\n---\n\n【共通仕様（抜粋）】\n{appendix}",
        choices="**ア** 1\n**イ** 2",
        correct="イ",
        explanation="e",
        category="科目B",
    )
    fallback, blocks = build_quiz_message(item)
    assert "共通仕様" not in fallback
    assert "if (条件)" not in fallback
    body_text = " ".join(
        b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"
    )
    assert "共通仕様" not in body_text


def test_build_quiz_message_kamoku_a_shows_text_and_figure_image() -> None:
    item = QuizItem(
        qid="ipa-2024r06-a-q03",
        qtype="科目A（IPA 2024r06）",
        body="図に示すようにキャッシュメモリと主記憶のアクセス時間が異なる。",
        choices="**ア** 0.75\n**イ** 1.0",
        correct="ア",
        explanation="e",
        category="科目A",
        image_urls=("https://example.com/page-3.png",),
        tags=("has_figure",),
    )
    fallback, blocks = build_quiz_message(item)
    assert "キャッシュメモリ" in fallback
    image_blocks = [b for b in blocks if b.get("type") == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["alt_text"] == "問題・図表 1"
    assert any(
        b.get("type") == "context" and "画像を参照" in b["elements"][0]["text"] for b in blocks
    )


def test_build_quiz_message_kamoku_a_plain_text_no_image() -> None:
    item = QuizItem(
        qid="ipa-a-plain",
        qtype="科目A",
        body="デッドロックの説明として適切なものはどれか。",
        choices="**ア** a\n**イ** b",
        correct="ア",
        explanation="e",
        category="科目A",
    )
    _fallback, blocks = build_quiz_message(item)
    assert not any(b.get("type") == "image" for b in blocks)


def test_build_quiz_message_kamoku_b_uses_image_not_text_body() -> None:
    item = QuizItem(
        qid="ipa-2024r06-b-q01",
        qtype="科目B（IPA 2024r06）",
        body="この長文は表示しない",
        choices="**ア** a\n**イ** b\n**ウ** c\n**エ** d",
        correct="ア",
        explanation="e",
        category="科目B",
        image_urls=("https://example.com/q01-page-03.png",),
    )
    fallback, blocks = build_quiz_message(item)
    assert "この長文は表示しない" not in fallback
    image_blocks = [b for b in blocks if b.get("type") == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["alt_text"] == "問題文 1"
    body_sections = [
        b
        for b in blocks
        if b.get("type") == "section" and "text" in b and "この長文" in b["text"].get("text", "")
    ]
    assert not body_sections


def test_build_quiz_message_shows_category_in_header() -> None:
    item = QuizItem(
        qid="ipa-q01",
        qtype="科目A（IPA 2023r05）",
        body="問題文",
        choices="**ア** a\n**イ** b",
        correct="ア",
        explanation="e",
        category="科目A",
    )
    _fallback, blocks = build_quiz_message(item)
    assert blocks[0]["text"]["text"] == "科目A 練習問題"
    meta = blocks[1]["elements"][0]["text"]
    assert "`ipa-q01`" in meta
    assert "科目A" in meta


def test_valid_image_urls_skips_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "febot.slack_handlers._image_url_reachable",
        lambda url: url.endswith("/ok.png"),
    )
    assert _valid_image_urls(("https://example.com/ok.png", "https://example.com/missing.png")) == (
        "https://example.com/ok.png",
    )


def test_build_quiz_message_kamoku_b_missing_images_shows_pdf_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("febot.slack_handlers._image_url_reachable", lambda _url: False)
    item = QuizItem(
        qid="ipa-b-missing",
        qtype="科目B",
        body="",
        choices="**ア** a\n**イ** b",
        correct="ア",
        explanation="e",
        category="科目B",
        image_urls=("https://example.com/missing.png",),
        source_url="https://example.com/exam.pdf",
    )
    fallback, blocks = build_quiz_message(item)
    assert "公式PDF" in fallback
    assert not any(b.get("type") == "image" for b in blocks)


def test_handle_quiz_button_grades_and_clears() -> None:
    sessions = ThreadSessionStore()
    channel = "C1"
    root = "100.0"
    key = thread_key(channel, root)
    item = QuizItem(
        qid="q1",
        qtype="単一",
        body="b",
        choices="**ア** a\n**イ** b",
        correct="イ",
        explanation="e",
    )
    sessions.set_quiz(key, item)
    replies: list[str] = []

    def say(msg: str, **kwargs) -> None:
        replies.append(msg)

    body = {
        "channel": {"id": channel},
        "message": {"ts": root, "thread_ts": None},
        "actions": [{"value": "イ"}],
    }
    assert handle_quiz_button(sessions, body, say) is True
    assert sessions.peek_quiz(key) is None
    assert len(replies) == 1
    assert "正解" in replies[0]
