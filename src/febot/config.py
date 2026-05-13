"""Environment-driven configuration. No secrets in code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv()


def _repo_root() -> Path:
    # src/febot/config.py -> repo root is parents[2]
    return Path(__file__).resolve().parents[2]


def _aws_credentials_available() -> bool:
    try:
        return boto3.Session().get_credentials() is not None
    except Exception:
        return False


def _should_use_bedrock() -> bool:
    """True if USE_BEDROCK is enabled, or BEDROCK_CHAT_MODEL_ID is set (chat on Bedrock; embed uses OpenAI API)."""
    raw = os.environ.get("USE_BEDROCK", "").strip().lower()
    if raw in ("0", "false", "no"):
        return False
    if raw in ("1", "true", "yes"):
        return True
    chat = os.environ.get("BEDROCK_CHAT_MODEL_ID", "").strip()
    return bool(chat)


@dataclass(frozen=True)
class Settings:
    slack_token: str
    slack_app_token: str
    use_bedrock: bool
    aws_region: str
    bedrock_chat_model_id: str
    bedrock_embedding_model_id: str
    bedrock_embedding_dimensions: int
    ai_api_key: str
    ai_base_url: str | None
    ai_chat_model: str
    ai_embedding_model: str
    chroma_path: Path
    corpus_dir: Path
    rag_top_k: int
    rate_limit_per_minute: int
    supabase_url: str
    supabase_key: str
    use_supabase: bool
    content_filter_enabled: bool

    @staticmethod
    def load(*, require_slack: bool = True) -> Settings:
        root = _repo_root()
        load_dotenv(root / ".env")
        slack_token = os.environ.get("SLACK_TOKEN", "").strip()
        slack_app_token = os.environ.get("SLACK_APP_TOKEN", "").strip()
        if require_slack:
            if not slack_token:
                raise RuntimeError("SLACK_TOKEN is required")
            if not slack_app_token:
                raise RuntimeError("SLACK_APP_TOKEN is required for Socket Mode")

        use_bedrock = _should_use_bedrock()

        region = (
            os.environ.get("AWS_REGION", "").strip()
            or os.environ.get("AWS_DEFAULT_REGION", "").strip()
            or "ap-northeast-1"
        )
        chat_model = (
            os.environ.get("BEDROCK_CHAT_MODEL_ID", "").strip()
            or "anthropic.claude-sonnet-4-6"
        )
        embed_model = (
            os.environ.get("BEDROCK_EMBEDDING_MODEL_ID", "").strip()
            or "amazon.titan-embed-text-v2:0"
        )
        embed_dims = int(os.environ.get("BEDROCK_EMBEDDING_DIMENSIONS", "1024"))

        ai_key = os.environ.get("AI_API_KEY", "").strip()
        base = os.environ.get("AI_BASE_URL", "").strip() or None
        ai_chat = os.environ.get("AI_CHAT_MODEL", "gpt-4o-mini").strip()
        ai_embed = os.environ.get("AI_EMBEDDING_MODEL", "text-embedding-3-small").strip()

        chroma = Path(os.environ.get("CHROMA_PATH", str(root / "data" / "chroma"))).resolve()
        corpus = Path(os.environ.get("CORPUS_DIR", str(root / "data" / "corpus"))).resolve()

        supabase_url = os.environ.get("SUPABASE_URL", "").strip()
        supabase_key = os.environ.get("SUPABASE_KEY", "").strip()
        use_supabase = bool(supabase_url and supabase_key)

        content_filter_enabled = os.environ.get(
            "CONTENT_FILTER_ENABLED", "true"
        ).strip().lower() in ("true", "1", "yes")

        return Settings(
            slack_token=slack_token,
            slack_app_token=slack_app_token,
            use_bedrock=use_bedrock,
            aws_region=region,
            bedrock_chat_model_id=chat_model,
            bedrock_embedding_model_id=embed_model,
            bedrock_embedding_dimensions=embed_dims,
            ai_api_key=ai_key,
            ai_base_url=base,
            ai_chat_model=ai_chat,
            ai_embedding_model=ai_embed,
            chroma_path=chroma,
            corpus_dir=corpus,
            rag_top_k=int(os.environ.get("RAG_TOP_K", "5")),
            rate_limit_per_minute=int(os.environ.get("RATE_LIMIT_PER_MINUTE", "20")),
            supabase_url=supabase_url,
            supabase_key=supabase_key,
            use_supabase=use_supabase,
            content_filter_enabled=content_filter_enabled,
        )

    def rag_enabled(self) -> bool:
        if self.use_bedrock:
            if not self.aws_region or not self.bedrock_chat_model_id:
                return False
            if not _aws_credentials_available():
                return False
            return bool(self.ai_api_key)
        return bool(self.ai_api_key)
