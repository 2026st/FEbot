"""Content filter to validate if questions are related to IT/programming topics."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from openai import OpenAI

from febot.config import Settings

logger = logging.getLogger(__name__)

FILTER_SYSTEM_PROMPT = """あなたは質問の内容を判定するフィルターです。
以下の基準で質問が適切かどうかを判定してください：

【許可する質問】
- 基本情報技術者試験に関する質問
- プログラミング全般に関する質問（Python, Java, C言語など）
- IT技術全般に関する質問（データベース、ネットワーク、セキュリティ、アルゴリズムなど）
- コンピュータサイエンスに関する質問

【拒否する質問】
- 上記以外の質問（天気、料理、観光、雑談など、IT・プログラミングに無関係な内容）

質問を判定し、以下のいずれかのみを返してください：
- 許可する場合: "OK"
- 拒否する場合: "NG"
"""


@dataclass
class FilterResult:
    """Content filter result."""

    is_valid: bool
    reason: str | None = None


class ContentFilter:
    """Filters questions to ensure they are related to IT/programming topics."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._oai = OpenAI(
            api_key=settings.ai_api_key,
            base_url=settings.ai_base_url,
        )

    def validate(self, question: str) -> FilterResult:
        """
        Validate if the question is related to IT/programming topics.

        Args:
            question: User's question to validate

        Returns:
            FilterResult with is_valid=True if question is acceptable
        """
        if not self._settings.content_filter_enabled:
            logger.debug("Content filter is disabled")
            return FilterResult(is_valid=True)

        if not question.strip():
            logger.warning("Empty question received")
            return FilterResult(is_valid=False, reason="Empty question")

        try:
            logger.info(f"Validating question: {question[:100]}...")

            response = self._oai.chat.completions.create(
                model=self._settings.ai_chat_model,
                messages=[
                    {"role": "system", "content": FILTER_SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                temperature=0.0,
                max_tokens=10,
            )

            result = (response.choices[0].message.content or "").strip().upper()
            logger.info(f"Filter result: {result}")

            if "OK" in result:
                return FilterResult(is_valid=True)
            else:
                return FilterResult(
                    is_valid=False,
                    reason="Question is not related to IT/programming topics",
                )

        except Exception as e:
            logger.error(f"Content filter error: {e}", exc_info=True)
            # Fail open: allow the question if filter fails
            return FilterResult(
                is_valid=True,
                reason=f"Filter error (fail-open): {e}",
            )
