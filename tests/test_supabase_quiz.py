"""Tests for Supabase quiz store row conversion."""

from febot.quiz import parse_choice_lines
from febot.supabase_quiz import (
    QuizChoice,
    QuizQuestionRecord,
    row_to_quiz_item,
)


def test_row_to_quiz_item() -> None:
    row = {
        "qid": "ipa-2023r05-b-q02",
        "body": "問題文",
        "choices": [
            {"mark": "ア", "text": "a"},
            {"mark": "ク", "text": "c"},
        ],
        "correct": "ク",
        "explanation": "解説",
        "category": "科目B",
        "field": "",
        "assets": [
            {
                "type": "image",
                "public_url": "https://example.com/fig.png",
                "storage_path": "ipa/2023r05/kamoku-b/q02/page-03.png",
                "page": 3,
            }
        ],
        "tags": ["quiz", "ipa", "kamoku_b", "has_figure"],
    }
    exam_meta = {
        "exam_id": "2023r05",
        "kamoku": "B",
        "source_pdf_qs_url": "https://ipa.example/qs.pdf",
    }
    item = row_to_quiz_item(row, exam_meta)
    assert item.qid == "ipa-2023r05-b-q02"
    assert item.correct == "ク"
    assert "ク" in item.choice_marks
    assert item.image_urls == ("https://example.com/fig.png",)
    assert "has_figure" in item.tags
    assert "2023r05" in item.qtype
    parsed = parse_choice_lines(item.choices)
    assert ("ク", "c") in parsed


def test_quiz_question_record_hash() -> None:
    rec = QuizQuestionRecord(
        qid="q1",
        question_number=1,
        category="科目A",
        field="",
        body="body",
        choices=[QuizChoice("ア", "a"), QuizChoice("イ", "b")],
        correct="ア",
        explanation="e",
        assets=[],
        tags=["quiz"],
    )
    h1 = rec.compute_hash()
    h2 = rec.compute_hash()
    assert h1 == h2
    assert len(h1) == 16
