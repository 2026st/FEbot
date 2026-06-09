"""Parse original practice questions from sample-questions.md."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class QuizItem:
    qid: str
    qtype: str
    body: str
    choices: str
    correct: str
    explanation: str


def parse_quiz_file(path: Path) -> list[QuizItem]:
    text = path.read_text(encoding="utf-8")
    starts = list(re.finditer(r"^id:\s*(\S+)\s*$", text, re.MULTILINE))
    items: list[QuizItem] = []
    for i, m in enumerate(starts):
        block_start = m.start()
        block_end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        block = text[block_start:block_end].strip()
        m_id = re.search(r"^id:\s*(\S+)", block, re.MULTILINE)
        m_type = re.search(r"^type:\s*(.+)$", block, re.MULTILINE)
        if not m_id:
            continue
        qid = m_id.group(1).strip()
        qtype = m_type.group(1).strip() if m_type else ""
        body_match = re.search(r"##\s*問[^\n]*\n+(.*?)(?=\*\*ア\*\*|\Z)", block, re.DOTALL)
        choices_match = re.search(r"(\*\*ア\*\*[\s\S]*?)(?=\*\*正解\*\*)", block)
        correct_match = re.search(r"\*\*正解\*\*:\s*([アイウエ])", block)
        expl_match = re.search(r"\*\*解説\*\*:\s*([\s\S]+?)(?=\n---|\Z)", block)
        if not (body_match and choices_match and correct_match and expl_match):
            continue
        body = body_match.group(1).strip()
        choices = choices_match.group(1).strip()
        correct = correct_match.group(1).strip()
        explanation = expl_match.group(1).strip()
        items.append(
            QuizItem(
                qid=qid,
                qtype=qtype,
                body=body,
                choices=choices,
                correct=correct,
                explanation=explanation,
            )
        )
    return items


def load_quiz_items() -> list[QuizItem]:
    """Practice questions are not loaded (local quiz data removed)."""
    return []


def pick_random(items: list[QuizItem]) -> QuizItem | None:
    if not items:
        return None
    return random.choice(items)


_CHOICE_LINE_RE = re.compile(r"^\*\*([アイウエ])\*\*\s*(.+)$")


def parse_choice_lines(choices: str) -> list[tuple[str, str]]:
    """Parse ``**ア** 本文`` lines into (mark, text) pairs."""
    result: list[tuple[str, str]] = []
    for line in choices.strip().splitlines():
        m = _CHOICE_LINE_RE.match(line.strip())
        if m:
            result.append((m.group(1), m.group(2).strip()))
    return result


_QUIZ_REPLY_STRICT_RE = re.compile(r"^([アイウエ])(?:[．.、,])?$")


def normalize_quiz_reply(text: str) -> str | None:
    """Strict quiz answer: single choice mark only (avoids grading「なぜウが…」as ウ)."""
    m = _QUIZ_REPLY_STRICT_RE.match(text.strip())
    return m.group(1) if m else None


def normalize_answer(text: str) -> str | None:
    """Loose extraction of a choice mark (non-quiz use)."""
    t = text.strip()
    for mark in ("ア", "イ", "ウ", "エ"):
        if t == mark or t.startswith(mark):
            return mark
    m = re.search(r"([アイウエ])", t)
    return m.group(1) if m else None
