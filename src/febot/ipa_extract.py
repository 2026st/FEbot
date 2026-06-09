"""Extract IPA past exam questions from PDF text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

# IPA choice marks (科目B may use ア〜ク and beyond)
IPA_MARKS_A = ("ア", "イ", "ウ", "エ")
IPA_MARKS_EXTENDED = (
    "ア",
    "イ",
    "ウ",
    "エ",
    "オ",
    "カ",
    "キ",
    "ク",
    "ケ",
    "コ",
    "サ",
    "シ",
    "ス",
    "セ",
    "ソ",
)

_ZEN_DIGIT = str.maketrans("１２３４５６７８９０", "1234567890")
_FIGURE_HINT_RE = re.compile(
    r"図\s*[0-9０-９]+|表\s*[0-9０-９]+|図表|次の図|次の表|図に示|表に示|"
    r"図の|表の|この図|この表|上の図|上の表|下の図|下の表|図を|表を"
)
_GARBLED_CHAR_RE = re.compile(r"[\uFFFD□�]")


@dataclass
class ExtractedQuestion:
    question_number: int
    body: str
    choices: list[tuple[str, str]]
    correct: str
    category: str
    has_figure_hint: bool = False
    appendix: str = ""
    pages: list[int] = field(default_factory=list)


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from PDF with page markers."""
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        parts.append(f"<!-- page {i + 1} -->\n\n{text}")
    return "\n\n".join(parts)


def pdf_page_count(pdf_path: Path) -> int:
    return len(PdfReader(str(pdf_path)).pages)


def _normalize_text(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text)
    text = re.sub(r"－\s*\d+\s*－", "", text)
    text = re.sub(r"©\d{4}[^\n]*\n", "", text)
    return text.translate(_ZEN_DIGIT)


def parse_ipa_answers(text: str) -> dict[int, str]:
    """Parse IPA answer text → {question_number: correct_mark}."""
    answers: dict[int, str] = {}
    marks = "|".join(re.escape(m) for m in IPA_MARKS_EXTENDED)
    for m in re.finditer(rf"問\s*(\d+)\s+({marks})", text):
        answers[int(m.group(1))] = m.group(2)
    return answers


def _marks_pattern(marks: tuple[str, ...]) -> str:
    return "|".join(re.escape(m) for m in marks)


def _split_choices(
    choices_raw: str, marks: tuple[str, ...] = IPA_MARKS_EXTENDED
) -> list[tuple[str, str]]:
    """Split choice block into (mark, text) pairs."""
    pattern = _marks_pattern(marks)
    found: list[tuple[str, str]] = []
    for m in re.finditer(rf"({pattern})[ \u3000]+", choices_raw):
        mark = m.group(1)
        start = m.end()
        next_m = re.search(rf"(?:{pattern})[ \u3000]", choices_raw[start:])
        end = start + next_m.start() if next_m else len(choices_raw)
        text = choices_raw[start:end].strip()
        if text:
            found.append((mark, text))
    return found


def _detect_figure_hint(text: str) -> bool:
    return bool(_FIGURE_HINT_RE.search(text))


def _detect_truth_table(text: str) -> bool:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    grid_lines = sum(1 for ln in lines if re.search(r"\b[01]\s+[01]", ln))
    logic_lines = sum(1 for ln in lines if re.search(r"\b(AND|OR|NOT|XOR)\b", ln, re.I))
    return grid_lines >= 2 or (grid_lines >= 1 and logic_lines >= 1)


def _detect_structured_table(text: str) -> bool:
    if text.count("|") >= 4:
        return True
    return bool(re.search(r"[／|\\├└─│]", text)) and text.count("\n") >= 3


def needs_visual_body(body: str, choices: list[tuple[str, str]] | None = None) -> bool:
    """True when problem text has figures/tables or symbols poorly shown as plain text."""
    parts = [body]
    if choices:
        parts.extend(text for _, text in choices)
    combined = "\n".join(parts)
    if _detect_figure_hint(combined):
        return True
    if _GARBLED_CHAR_RE.search(combined):
        return True
    if _detect_truth_table(combined):
        return True
    return bool(_detect_structured_table(combined))


def parse_ipa_kamoku_a(qs_text: str, ans_text: str, exam_id: str) -> list[ExtractedQuestion]:
    """Parse IPA 科目A questions from extracted PDF text."""
    text = _normalize_text(qs_text)
    answers = parse_ipa_answers(_normalize_text(ans_text))

    q_starts = list(re.finditer(r"(?m)^[ \t]*問(\d+)\s+", text))
    items: list[ExtractedQuestion] = []

    for i, m in enumerate(q_starts):
        q_num = int(m.group(1))
        block_start = m.start()
        block_end = q_starts[i + 1].start() if i + 1 < len(q_starts) else len(text)
        block = text[block_start:block_end].strip()

        choice_m = re.search(r"(?<![ア-ン])ア[ \u3000]", block)
        if not choice_m:
            continue

        body = re.sub(r"^問\d+\s+", "", block[: choice_m.start()]).strip()
        choices_raw = block[choice_m.start() :].strip()
        choices = _split_choices(choices_raw, IPA_MARKS_A)

        correct = answers.get(q_num, "")
        if not correct or not body or len(choices) < 2:
            continue

        items.append(
            ExtractedQuestion(
                question_number=q_num,
                body=body,
                choices=choices,
                correct=correct,
                category="科目A",
                has_figure_hint=needs_visual_body(body, choices),
            )
        )

    return items


def parse_ipa_kamoku_b(qs_text: str, ans_text: str, exam_id: str) -> list[ExtractedQuestion]:
    """Parse IPA 科目B questions from extracted PDF text."""
    text = _normalize_text(qs_text)
    answers = parse_ipa_answers(_normalize_text(ans_text))

    q_starts = list(re.finditer(r"(?m)^[ \t]*問(\d+)\s+", text))

    # 科目B は冒頭に擬似言語仕様がある（末尾付録ではない）
    appendix = ""
    appendix_m = re.search(r"(擬似言語|疑似言語)", text)
    if appendix_m and q_starts:
        first_q_pos = q_starts[0].start()
        if appendix_m.start() < first_q_pos:
            appendix = text[appendix_m.start() : first_q_pos].strip()

    items: list[ExtractedQuestion] = []

    for i, m in enumerate(q_starts):
        q_num = int(m.group(1))
        block_start = m.start()
        block_end = q_starts[i + 1].start() if i + 1 < len(q_starts) else len(text)
        block = text[block_start:block_end].strip()

        choice_m = re.search(r"(?<![ア-ン])ア[ \u3000]", block)
        if not choice_m:
            continue

        body = re.sub(r"^問\d+\s+", "", block[: choice_m.start()]).strip()
        choices_raw = block[choice_m.start() :].strip()
        choices = _split_choices(choices_raw, IPA_MARKS_EXTENDED)

        correct = answers.get(q_num, "")
        if not correct or not body or len(choices) < 2:
            continue

        items.append(
            ExtractedQuestion(
                question_number=q_num,
                body=body,
                choices=choices,
                correct=correct,
                category="科目B",
                has_figure_hint=needs_visual_body(body, choices),
                appendix=appendix[:500] if appendix else "",
            )
        )

    return items


def extracted_to_qid(exam_id: str, kamoku: str, q_num: int) -> str:
    k = kamoku.lower()
    return f"ipa-{exam_id}-{k}-q{q_num:02d}"


def build_default_tags(exam_id: str, kamoku: str, has_figure: bool) -> list[str]:
    tags = ["quiz", "ipa", f"exam_{exam_id}", f"kamoku_{kamoku.lower()}"]
    if has_figure:
        tags.append("has_figure")
    return tags
