"""Environment-driven configuration. No secrets in code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _repo_root() -> Path:
    # src/febot/config.py -> repo root is parents[2]
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    slack_token: str
    slack_app_token: str
    ai_api_key: str
    ai_base_url: str | None
    ai_chat_model: str
    ai_embedding_model: str
    chroma_path: Path
    corpus_dir: Path
    rag_top_k: int
    rate_limit_per_minute: int

    @staticmethod
    def load(*, require_slack: bool = True) -> Settings:
        root = _repo_root()
        load_dotenv(root / ".env")
        slack_token = os.environ.get("SLACK_TOKEN", "").strip()
        slack_app_token = os.environ.get("SLACK_APP_TOKEN", "").strip()
        ai_key = os.environ.get("AI_API_KEY", "").strip()
        if require_slack:
            if not slack_token:
                raise RuntimeError("SLACK_TOKEN is required")
            if not slack_app_token:
                raise RuntimeError("SLACK_APP_TOKEN is required for Socket Mode")

        base = os.environ.get("AI_BASE_URL", "").strip() or None
        chroma = Path(
            os.environ.get("CHROMA_PATH", str(root / "data" / "chroma"))
        ).resolve()
        corpus = Path(
            os.environ.get("CORPUS_DIR", str(root / "data" / "corpus"))
        ).resolve()

        return Settings(
            slack_token=slack_token,
            slack_app_token=slack_app_token,
            ai_api_key=ai_key,
            ai_base_url=base,
            ai_chat_model=os.environ.get("AI_CHAT_MODEL", "gpt-4o-mini").strip(),
            ai_embedding_model=os.environ.get(
                "AI_EMBEDDING_MODEL", "text-embedding-3-small"
            ).strip(),
            chroma_path=chroma,
            corpus_dir=corpus,
            rag_top_k=int(os.environ.get("RAG_TOP_K", "5")),
            rate_limit_per_minute=int(os.environ.get("RATE_LIMIT_PER_MINUTE", "20")),
        )

    def rag_enabled(self) -> bool:
        return bool(self.ai_api_key)
