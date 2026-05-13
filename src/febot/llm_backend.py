"""LLM + embedding backends: Amazon Bedrock or OpenAI-compatible API."""

from __future__ import annotations

from typing import Protocol

from openai import OpenAI

from febot.bedrock_client import BedrockClient
from febot.config import Settings


class ChatEmbedBackend(Protocol):
    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float,
        max_tokens: int | None,
    ) -> str: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class OpenAICompatBackend:
    """OpenAI-compatible chat + embeddings (same interface as BedrockClient)."""

    def __init__(self, settings: Settings) -> None:
        self._client = OpenAI(api_key=settings.ai_api_key, base_url=settings.ai_base_url)
        self._chat_model = settings.ai_chat_model
        self._embed_model = settings.ai_embedding_model

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        kwargs: dict = {
            "model": self._chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        response = self._client.chat.completions.create(**kwargs)
        return (response.choices[0].message.content or "").strip()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._embed_model, input=texts)
        return [e.embedding for e in sorted(resp.data, key=lambda x: x.index)]


def get_llm_backend(settings: Settings) -> ChatEmbedBackend:
    """Bedrock if configured; otherwise OpenAI-compatible (requires AI_API_KEY when not Bedrock)."""
    if settings.use_bedrock:
        return BedrockClient(settings)
    return OpenAICompatBackend(settings)
