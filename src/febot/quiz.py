"""Quiz items: load from Supabase, pick/filter, answer normalization."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

_FIELD_MAP = {
    "os": "OS",
    "net": "ネットワーク",
    "db": "データベース",
    "sec": "セキュリティ",
    "algo": "アルゴリズム",
    "sheet": "表計算",
    "hw": "ハードウェア",
    "sw": "ソフトウェア",
}


KNOWN_FIELDS = sorted(set(_FIELD_MAP.values()))

KNOWN_CATEGORIES = ["科目A", "科目B"]


DEFAULT_CHOICE_MARKS = ("ア", "イ", "ウ", "エ")

_COMMON_SPEC_SECTION_RE = re.compile(
    r"\n\n---\n\n【共通仕様（抜粋）】\n.*",
    re.DOTALL,
)


def strip_quiz_common_spec(body: str) -> str:
    """Remove embedded IPA pseudo-language appendix from quiz display body."""
    return _COMMON_SPEC_SECTION_RE.sub("", body).rstrip()


# IPA extended marks for multi-choice (科目B)

IPA_CHOICE_MARKS = (
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


@dataclass(frozen=True)
class QuizItem:
    qid: str

    qtype: str

    body: str

    choices: str

    correct: str

    explanation: str

    category: str = ""  # "科目A" | "科目B" | ""

    field: str = ""  # e.g. "OS", "ネットワーク", ""

    image_urls: tuple[str, ...] = ()

    source_url: str = ""

    tags: tuple[str, ...] = ()

    @property
    def choice_marks(self) -> tuple[str, ...]:

        parsed = parse_choice_lines(self.choices)

        if parsed:
            return tuple(m for m, _ in parsed)

        return DEFAULT_CHOICE_MARKS


def format_qtype(category: str, exam_id: str = "", kamoku: str = "") -> str:

    if exam_id and kamoku:
        return f"{category}（IPA {exam_id} 科目{kamoku}）"

    if category:
        return category

    return "練習問題"


def choices_to_markdown(choices: list[tuple[str, str]]) -> str:

    return "\n".join(f"**{m}** {t}" for m, t in choices)


def _field_from_qid(qid: str) -> str:

    for part in qid.split("-"):
        if part.lower() in _FIELD_MAP:
            return _FIELD_MAP[part.lower()]

    return ""


def _category_from_qtype(qtype: str) -> str:

    return "科目B" if "科目B" in qtype else "科目A"


def parse_quiz_file(path: Path) -> list[QuizItem]:
    """Parse local sample-questions.md (dev/test only)."""

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

        correct_match = re.search(r"\*\*正解\*\*:\s*([アイウエオカキクケコサシスセソ])", block)

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
                category=_category_from_qtype(qtype),
                field=_field_from_qid(qid),
                tags=("quiz", "original"),
            )
        )

    return items


def load_quiz_items_from_supabase(store) -> list[QuizItem]:
    """Load all quiz items from Supabase (``SupabaseQuizStore``)."""
    return store.load_all()


def load_quiz_items(quiz_dir: Path) -> list[QuizItem]:
    """Load from local files (dev/test fallback)."""

    items: list[QuizItem] = []

    sample_path = quiz_dir / "sample-questions.md"

    if sample_path.is_file():
        items.extend(parse_quiz_file(sample_path))

    return items


def pick_random(items: list[QuizItem]) -> QuizItem | None:

    if not items:
        return None

    return random.choice(items)


def pick_filtered(items: list[QuizItem], option: str) -> QuizItem | None:
    """Pick a random QuizItem matching option."""

    opt = option.strip()

    if not opt:
        return pick_random(items)

    opt_lower = opt.lower()

    if opt_lower in ("科目a", "a", "午前") or opt == "科目A":
        filtered = [it for it in items if it.category == "科目A"]

    elif opt_lower in ("科目b", "b", "午後") or opt == "科目B":
        filtered = [it for it in items if it.category == "科目B"]

    else:
        filtered = [
            it
            for it in items
            if opt in it.field
            or opt_lower in it.field.lower()
            or opt in it.qtype
            or opt_lower in it.qtype.lower()
            or any(opt in t or opt_lower in t.lower() for t in it.tags)
        ]

    return pick_random(filtered) if filtered else None


_CHOICE_LINE_RE = re.compile(r"^\*\*([ア-ン])\*\*\s*(.+)$")


def parse_choice_lines(choices: str) -> list[tuple[str, str]]:
    """Parse ``**ア** 本文`` lines into (mark, text) pairs."""

    result: list[tuple[str, str]] = []

    for line in choices.strip().splitlines():
        m = _CHOICE_LINE_RE.match(line.strip())

        if m:
            result.append((m.group(1), m.group(2).strip()))

    return result


def normalize_answer(text: str, allowed_marks: tuple[str, ...] | None = None) -> str | None:
    """Loose extraction of a choice mark (non-quiz use)."""

    marks = allowed_marks or IPA_CHOICE_MARKS

    t = text.strip()

    for mark in marks:
        if t == mark or t.startswith(mark):
            return mark

    pattern = "(" + "|".join(re.escape(m) for m in marks) + ")"

    m = re.search(pattern, t)

    return m.group(1) if m else None


def normalize_quiz_reply(
    text: str,
    allowed_marks: tuple[str, ...] | None = None,
) -> str | None:
    """Strict extraction: bare choice mark with optional trailing punctuation."""

    marks = allowed_marks or DEFAULT_CHOICE_MARKS

    pattern = "(" + "|".join(re.escape(m) for m in marks) + ")"

    m = re.fullmatch(pattern + r"[、。．.,\s]*", text.strip())

    return m.group(1) if m else None
