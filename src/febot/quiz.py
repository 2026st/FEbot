"""Parse practice questions from sample-questions.md and IPA past exam files."""

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

# Full-width digit → ASCII digit (問１ → 問1)
_ZEN_DIGIT = str.maketrans("１２３４５６７８９０", "1234567890")


@dataclass(frozen=True)
class QuizItem:
    qid: str
    qtype: str
    body: str
    choices: str
    correct: str
    explanation: str
    category: str = ""  # "科目A" | "科目B" | ""
    field: str = ""     # e.g. "OS", "ネットワーク", "" (empty for IPA questions)


def _field_from_qid(qid: str) -> str:
    for part in qid.split("-"):
        if part.lower() in _FIELD_MAP:
            return _FIELD_MAP[part.lower()]
    return ""


def _category_from_qtype(qtype: str) -> str:
    return "科目B" if "科目B" in qtype else "科目A"


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
                category=_category_from_qtype(qtype),
                field=_field_from_qid(qid),
            )
        )
    return items


def _parse_ipa_answers(ans_path: Path) -> dict[int, str]:
    """Parse IPA answer file → {question_number: correct_choice}."""
    text = ans_path.read_text(encoding="utf-8")
    answers: dict[int, str] = {}
    for m in re.finditer(r"問\s*(\d+)\s+([アイウエ])", text):
        answers[int(m.group(1))] = m.group(2)
    return answers


def _parse_ipa_kamoku_a(qs_path: Path, ans_path: Path, source_label: str) -> list[QuizItem]:
    """Parse IPA 科目A past exam file into QuizItems (best-effort PDF text extraction)."""
    text = qs_path.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text)
    text = re.sub(r"－\s*\d+\s*－", "", text)
    text = re.sub(r"©\d{4}[^\n]*\n", "", text)
    text = text.translate(_ZEN_DIGIT)

    answers = _parse_ipa_answers(ans_path)

    q_starts = list(re.finditer(r"(?m)^[ \t]*問(\d+)\s+", text))
    items: list[QuizItem] = []

    for i, m in enumerate(q_starts):
        q_num = int(m.group(1))
        block_start = m.start()
        block_end = q_starts[i + 1].start() if i + 1 < len(q_starts) else len(text)
        block = text[block_start:block_end].strip()

        # Choices begin at the first standalone ア followed by a non-kana character
        choice_m = re.search(r"(?<![ア-ン])ア[ \u3000]", block)
        if not choice_m:
            continue

        body = re.sub(r"^問\d+\s+", "", block[: choice_m.start()]).strip()
        choices_raw = block[choice_m.start():].strip()
        # Ensure each choice option starts on its own line
        choices_fmt = re.sub(r"\s+([イウエ])[ \u3000]", r"\n\1 ", choices_raw).strip()
        choices_fmt = re.sub(r"^([アイウエ])[ \u3000]", r"**\1** ", choices_fmt, flags=re.MULTILINE)

        correct = answers.get(q_num, "")
        if not correct or not body:
            continue

        items.append(
            QuizItem(
                qid=f"ipa-{source_label}-q{q_num:02d}",
                qtype=f"科目A（IPA {source_label}）",
                body=body,
                choices=choices_fmt,
                correct=correct,
                explanation=f"正解: {correct}（IPA公式解答より）\n※ 図表を含む問題は選択肢のみ表示しています。正確な問題文は公式PDFでご確認ください。",
                category="科目A",
                field="",
            )
        )

    return items


def load_quiz_items(corpus_dir: Path) -> list[QuizItem]:
    items: list[QuizItem] = []

    sample_path = corpus_dir / "sample-questions.md"
    if sample_path.is_file():
        items.extend(parse_quiz_file(sample_path))

    ipa_pairs = [
        (
            "ipa-fe-2023r05-cbt-kamoku-a-qs.md",
            "ipa-fe-2023r05-cbt-kamoku-a-ans.md",
            "2023r05",
        ),
    ]
    for qs_name, ans_name, label in ipa_pairs:
        qs_path = corpus_dir / qs_name
        ans_path = corpus_dir / ans_name
        if qs_path.is_file() and ans_path.is_file():
            items.extend(_parse_ipa_kamoku_a(qs_path, ans_path, label))

    return items


def pick_random(items: list[QuizItem]) -> QuizItem | None:
    if not items:
        return None
    return random.choice(items)


def pick_filtered(items: list[QuizItem], option: str) -> QuizItem | None:
    """Pick a random QuizItem matching option.

    Supported option values:
      "科目A" / "A" / "a" / "午前"  → 科目A questions only
      "科目B" / "B" / "b" / "午後"  → 科目B questions only
      other text                    → substring match against field or qtype
      ""                            → random from all
    """
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
            it for it in items
            if opt in it.field or opt_lower in it.field.lower()
            or opt in it.qtype or opt_lower in it.qtype.lower()
        ]

    return pick_random(filtered) if filtered else None


def normalize_answer(text: str) -> str | None:
    """Loose extraction of a choice mark (non-quiz use)."""
    t = text.strip()
    for mark in ("ア", "イ", "ウ", "エ"):
        if t == mark or t.startswith(mark):
            return mark
    m = re.search(r"([アイウエ])", t)
    return m.group(1) if m else None
