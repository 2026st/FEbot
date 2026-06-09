"""Render PDF pages to PNG for quiz figure display."""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_RENDER_DPI = 150
_ZEN_DIGIT = str.maketrans("１２３４５６７８９０", "1234567890")


def _page_starts_question(text: str, q_num: int) -> bool:
    norm = text.translate(_ZEN_DIGIT)
    return bool(re.search(rf"(?m)^\s*問\s*{q_num}\s+", norm)) or bool(
        re.search(rf"(?m)^\s*第\s*{q_num}\s+", norm)
    )


def capture_pdf_pages(
    pdf_path: Path,
    output_dir: Path,
    *,
    max_pages: int = 30,
    dpi: int = DEFAULT_RENDER_DPI,
) -> dict[int, Path]:
    """Render each page of a local PDF to PNG. Returns {page_number: image_path}."""
    try:
        import fitz  # pymupdf
    except ImportError as e:
        raise RuntimeError(
            'pymupdf is required for figure capture. Install: pip install -e ".[ingest]"'
        ) from e

    from febot.ipa_extract import pdf_page_count

    output_dir.mkdir(parents=True, exist_ok=True)
    num_pages = min(pdf_page_count(pdf_path), max_pages)
    results: dict[int, Path] = {}
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)

    with fitz.open(pdf_path) as doc:
        for page_num in range(1, num_pages + 1):
            page = doc[page_num - 1]
            pix = page.get_pixmap(matrix=matrix)
            out_path = output_dir / f"page-{page_num:02d}.png"
            pix.save(str(out_path))
            results[page_num] = out_path
            log.info("Rendered PDF page %d -> %s", page_num, out_path)

    return results


def assign_question_pages(
    pdf_path: Path,
    q_nums: list[int],
    *,
    boundary_q_nums: list[int] | None = None,
) -> dict[int, list[int]]:
    """Map question numbers to PDF page(s) by locating 問N / 第N in page text."""
    try:
        import fitz  # pymupdf
    except ImportError as e:
        raise RuntimeError(
            'pymupdf is required for figure capture. Install: pip install -e ".[ingest]"'
        ) from e

    target_nums = sorted(set(q_nums))
    all_nums = sorted(set(boundary_q_nums or target_nums))
    if not target_nums:
        return {}

    start_page: dict[int, int] = {}
    with fitz.open(pdf_path) as doc:
        num_pages = len(doc)
        for idx in range(num_pages):
            text = doc[idx].get_text()
            for q_num in all_nums:
                if q_num not in start_page and _page_starts_question(text, q_num):
                    start_page[q_num] = idx + 1

        full_mapping: dict[int, list[int]] = {}
        for i, q_num in enumerate(all_nums):
            start = start_page.get(q_num)
            if not start:
                continue
            if i + 1 < len(all_nums) and all_nums[i + 1] in start_page:
                next_start = start_page[all_nums[i + 1]]
                end = next_start - 1 if next_start > start else start
            else:
                end = num_pages
            full_mapping[q_num] = list(range(start, end + 1))

        return {n: full_mapping[n] for n in target_nums if n in full_mapping}


def assign_kamoku_b_question_pages(pdf_path: Path, questions: list) -> dict[int, list[int]]:
    """Map each 科目B question to all PDF pages for that question block."""
    all_nums = sorted({q.question_number for q in questions})
    return assign_question_pages(pdf_path, all_nums, boundary_q_nums=all_nums)


def assign_kamoku_a_visual_pages(pdf_path: Path, questions: list) -> dict[int, list[int]]:
    """Map 科目A questions that need visuals (figures / special symbols) to PDF pages."""
    all_nums = sorted({q.question_number for q in questions})
    visual_nums = [q.question_number for q in questions if q.has_figure_hint]
    return assign_question_pages(pdf_path, visual_nums, boundary_q_nums=all_nums)


def assign_figure_pages(
    questions: list,
    page_screenshots: dict[int, Path],
) -> dict[int, list[int]]:
    """Legacy heuristic mapper (prefer assign_question_pages)."""
    if not page_screenshots:
        return {}

    pages = sorted(page_screenshots.keys())
    mapping: dict[int, list[int]] = {}
    q_nums = sorted(q.question_number for q in questions if q.has_figure_hint)

    if not q_nums:
        return mapping

    content_pages = [p for p in pages if p >= 3] or pages
    for i, q_num in enumerate(q_nums):
        page_idx = min(i, len(content_pages) - 1)
        mapping[q_num] = [content_pages[page_idx]]

    return mapping
