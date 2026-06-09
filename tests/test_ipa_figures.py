"""Tests for IPA quiz figure capture."""

from pathlib import Path

from pypdf import PdfWriter

from febot.ipa_figures import (
    assign_figure_pages,
    assign_kamoku_a_visual_pages,
    assign_kamoku_b_question_pages,
    assign_question_pages,
    capture_pdf_pages,
)


class _FakeQuestion:
    def __init__(self, question_number: int, has_figure_hint: bool) -> None:
        self.question_number = question_number
        self.has_figure_hint = has_figure_hint


def test_capture_pdf_pages_renders_png(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with pdf_path.open("wb") as f:
        writer.write(f)

    out_dir = tmp_path / "figures"
    results = capture_pdf_pages(pdf_path, out_dir, max_pages=1)

    assert 1 in results
    assert results[1].is_file()
    assert results[1].stat().st_size > 0


def test_assign_figure_pages_skips_cover_pages() -> None:
    screenshots = {1: Path("p1.png"), 2: Path("p2.png"), 3: Path("p3.png"), 4: Path("p4.png")}
    questions = [
        _FakeQuestion(1, True),
        _FakeQuestion(2, True),
    ]
    mapping = assign_figure_pages(questions, screenshots)
    assert mapping[1] == [3]
    assert mapping[2] == [4]


def test_assign_kamoku_b_question_pages_from_cached_pdf() -> None:
    pdf_path = Path("data/.ipa_cache/2024r06-kamoku-b-qs.pdf")
    if not pdf_path.is_file():
        return
    questions = [_FakeQuestion(n, False) for n in range(1, 7)]
    mapping = assign_kamoku_b_question_pages(pdf_path, questions)
    assert len(mapping) == 6
    for q_num in range(1, 7):
        assert q_num in mapping
        assert mapping[q_num]


def test_assign_question_pages_same_page_questions() -> None:
    pdf_path = Path("data/.ipa_cache/2024r06-kamoku-a-qs.pdf")
    if not pdf_path.is_file():
        return
    mapping = assign_question_pages(pdf_path, [1, 2], boundary_q_nums=list(range(1, 21)))
    assert mapping[1] == [2]
    assert mapping[2] == [2]


def test_assign_kamoku_a_visual_pages_subset() -> None:
    pdf_path = Path("data/.ipa_cache/2024r06-kamoku-a-qs.pdf")
    if not pdf_path.is_file():
        return
    questions = [_FakeQuestion(n, n in (1, 3)) for n in range(1, 21)]
    mapping = assign_kamoku_a_visual_pages(pdf_path, questions)
    assert set(mapping.keys()) == {1, 3}
    assert mapping[1] == [2]
    assert mapping[3] == [3]
