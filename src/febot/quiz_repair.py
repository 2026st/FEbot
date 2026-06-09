"""LLM-assisted repair of IPA extracted quiz questions."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from febot.ipa_extract import IPA_MARKS_EXTENDED, ExtractedQuestion
from febot.llm_backend import ChatEmbedBackend

log = logging.getLogger(__name__)

_REPAIR_SYSTEM = """あなたは基本情報技術者試験の過去問データ整備担当です。
IPA公式PDFから機械抽出した問題データを、公式解答と照合して修正してください。

ルール:
- 正解マークは公式解答を最優先（変更しない）
- 問題文・選択肢の誤字・欠落・改行崩れを補正する
- 図表の内容は本文に含めず、図表参照がある場合はその旨を1文追記してよい
- 推測で新しい選択肢を追加しない
- 出力は JSON のみ（説明文なし）

JSONスキーマ:
{
  "questions": [
    {
      "question_number": 1,
      "body": "問題文",
      "choices": [{"mark": "ア", "text": "..."}, ...],
      "correct": "イ",
      "explanation": "正解理由の簡潔な解説"
    }
  ]
}
"""


@dataclass
class RepairedQuestion:
    question_number: int
    body: str
    choices: list[tuple[str, str]]
    correct: str
    explanation: str


def _parse_llm_json(raw: str) -> dict:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def _validate_choices(choices: list[dict]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for c in choices:
        mark = c.get("mark", "")
        text = c.get("text", "").strip()
        if mark in IPA_MARKS_EXTENDED and text:
            result.append((mark, text))
    return result


def extracted_to_repaired(
    extracted: list,
    *,
    source_pdf_qs_url: str = "",
) -> list[RepairedQuestion]:
    """Build RepairedQuestion list from raw extraction (no LLM)."""
    return [
        RepairedQuestion(
            question_number=q.question_number,
            body=q.body,
            choices=q.choices,
            correct=q.correct,
            explanation=(
                f"正解: {q.correct}（IPA公式解答より）\n"
                f"※ 図表を含む問題は公式PDFでご確認ください。\n"
                f"出典: {source_pdf_qs_url or 'IPA公式過去問'}"
            ),
        )
        for q in extracted
    ]


def repair_questions(
    llm: ChatEmbedBackend,
    extracted: list[ExtractedQuestion],
    ans_text: str,
    *,
    exam_id: str,
    kamoku: str,
    source_pdf_qs_url: str = "",
) -> list[RepairedQuestion]:
    """Use LLM to repair extracted questions; fall back to raw on failure."""
    if not extracted:
        return []

    raw_payload = {
        "exam_id": exam_id,
        "kamoku": kamoku,
        "source_pdf": source_pdf_qs_url,
        "official_answers_text": ans_text[:8000],
        "extracted_questions": [
            {
                "question_number": q.question_number,
                "body": q.body,
                "choices": [{"mark": m, "text": t} for m, t in q.choices],
                "correct": q.correct,
            }
            for q in extracted
        ],
    }

    try:
        response = llm.chat(
            _REPAIR_SYSTEM,
            json.dumps(raw_payload, ensure_ascii=False, indent=2),
            temperature=0.1,
            max_tokens=16000,
        )
        data = _parse_llm_json(response)
        repaired: list[RepairedQuestion] = []
        by_num = {q.question_number: q for q in extracted}

        for item in data.get("questions", []):
            q_num = int(item["question_number"])
            orig = by_num.get(q_num)
            if not orig:
                continue
            choices = _validate_choices(item.get("choices", []))
            if len(choices) < 2:
                choices = orig.choices
            correct = orig.correct  # always trust official answer key
            body = item.get("body", "").strip() or orig.body
            explanation = item.get("explanation", "").strip()
            if not explanation:
                explanation = (
                    f"正解: {correct}（IPA公式解答より）\n"
                    f"出典: {source_pdf_qs_url or 'IPA公式過去問'}"
                )
            repaired.append(
                RepairedQuestion(
                    question_number=q_num,
                    body=body,
                    choices=choices,
                    correct=correct,
                    explanation=explanation,
                )
            )

        if len(repaired) >= len(extracted) * 0.8:
            log.info("LLM repaired %d/%d questions", len(repaired), len(extracted))
            return sorted(repaired, key=lambda x: x.question_number)

    except Exception as e:
        log.warning("LLM repair failed, using raw extraction: %s", e)

    return extracted_to_repaired(extracted, source_pdf_qs_url=source_pdf_qs_url)
