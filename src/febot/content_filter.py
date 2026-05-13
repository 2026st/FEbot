"""Content filter to validate if questions are related to IT/programming topics."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from febot.config import Settings
from febot.llm_backend import get_llm_backend

logger = logging.getLogger(__name__)

FILTER_SYSTEM_PROMPT = """あなたは質問の内容を判定するフィルターです。
以下の基準で質問が適切かどうかを判定してください：

【許可する質問】
- 基本情報技術者試験に関する質問
- プログラミング全般に関する質問（Python, Java, C言語など）
- IT技術全般に関する質問（データベース、ネットワーク、セキュリティ、アルゴリズム、クラウド、API、サーバーなど）
- コンピュータサイエンスに関する質問
- IT用語が含まれている質問（日常語と同じ言葉でもIT文脈の可能性があるもの）

【判定のポイント】
- 「クラウド」「キャッシュ」「ハッシュ」「リンク」などは日常語とIT用語の両方で使われるが、質問文にこれらが含まれていればIT関連の可能性が高いと判断する
- 「～とは？」という定義質問は、IT用語の定義を聞いている可能性が高い

【拒否する質問】
- 明らかにIT・プログラミングに無関係な内容（天気、料理、観光、雑談など）
- IT用語が一切含まれず、日常的な話題のみの質問

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
        self._llm = get_llm_backend(settings)

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

            result_text = self._llm.chat(
                FILTER_SYSTEM_PROMPT,
                question,
                temperature=0.0,
                max_tokens=10,
            )

            result = result_text.strip().upper()
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
