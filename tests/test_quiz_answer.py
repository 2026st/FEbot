"""Tests for quiz answer normalization."""

from febot.quiz import normalize_answer, normalize_quiz_reply


def test_normalize_quiz_reply_strict() -> None:
    assert normalize_quiz_reply("イ") == "イ"
    assert normalize_quiz_reply("ウ.") == "ウ"
    assert normalize_quiz_reply("ア、") == "ア"
    assert normalize_quiz_reply("なぜウが違うの？") is None
    assert normalize_quiz_reply("イです") is None
    assert normalize_quiz_reply("") is None


def test_normalize_answer_loose() -> None:
    assert normalize_answer("イ") == "イ"
    assert normalize_answer("なぜウが違う") == "ウ"
