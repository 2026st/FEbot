"""Tests for LLM backend selection."""

from febot.config import Settings
from febot.llm_backend import (
    BedrockChatOpenAIEmbedBackend,
    OpenAICompatBackend,
    get_llm_backend,
    get_openai_compat_backend,
)


def _settings(**overrides) -> Settings:
    base = dict(
        slack_token="x",
        slack_app_token="x",
        use_bedrock=True,
        aws_region="ap-northeast-1",
        bedrock_chat_model_id="anthropic.claude-3-5-haiku-20241022-v1:0",
        bedrock_embedding_model_id="amazon.titan-embed-text-v2:0",
        bedrock_embedding_dimensions=1024,
        bedrock_chat_skip_converse=False,
        ai_api_key="sk-test",
        ai_base_url=None,
        ai_chat_model="gpt-4o-mini",
        ai_embedding_model="text-embedding-3-small",
        chroma_path=__import__("pathlib").Path("."),
        corpus_dir=__import__("pathlib").Path("."),
        quiz_dir=__import__("pathlib").Path("."),
        rag_top_k=5,
        rate_limit_per_minute=20,
        supabase_url="",
        supabase_key="",
        supabase_service_key="",
        use_supabase=False,
        content_filter_enabled=True,
    )
    base.update(overrides)
    return Settings(**base)


def test_get_llm_backend_uses_bedrock_when_enabled() -> None:
    backend = get_llm_backend(_settings(use_bedrock=True))
    assert isinstance(backend, BedrockChatOpenAIEmbedBackend)


def test_get_openai_compat_backend_ignores_bedrock() -> None:
    backend = get_openai_compat_backend(_settings(use_bedrock=True))
    assert isinstance(backend, OpenAICompatBackend)
