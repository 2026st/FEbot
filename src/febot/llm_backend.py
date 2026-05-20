"""LLM + embedding backends: Amazon Bedrock or OpenAI-compatible API."""

from __future__ import annotations

import logging
from typing import Protocol

from openai import OpenAI

from febot.bedrock_client import BedrockClient
from febot.config import Settings

log = logging.getLogger(__name__)


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
        log.info(
            "使用AI chat: provider=openai-compatible model=%s base_url=%s",
            self._chat_model,
            str(self._client.base_url).rstrip("/"),
        )
        response = self._client.chat.completions.create(**kwargs)
        return (response.choices[0].message.content or "").strip()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        log.info(
            "使用AI embed: provider=openai-compatible model=%s texts=%d",
            self._embed_model,
            len(texts),
        )
        resp = self._client.embeddings.create(model=self._embed_model, input=texts)
        return [e.embedding for e in sorted(resp.data, key=lambda x: x.index)]


class BedrockChatOpenAIEmbedBackend:
    """Bedrock for chat; OpenAI-compatible API for embeddings (RAG)."""

    def __init__(self, settings: Settings) -> None:
        self._chat = BedrockClient(settings)
        self._embed = OpenAICompatBackend(settings)

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        return self._chat.chat(system, user, temperature=temperature, max_tokens=max_tokens)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._embed.embed_texts(texts)


def get_llm_backend(settings: Settings) -> ChatEmbedBackend:
    """Bedrock chat if configured; embeddings always use OpenAI-compatible API when Bedrock is on."""
    if settings.use_bedrock:
        return BedrockChatOpenAIEmbedBackend(settings)
    return OpenAICompatBackend(settings)
