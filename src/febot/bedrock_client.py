"""Amazon Bedrock Runtime: Claude (chat) + Titan (embeddings)."""

from __future__ import annotations

import json
import logging

import boto3
from botocore.exceptions import ClientError

from febot.config import Settings

log = logging.getLogger(__name__)


class BedrockClient:
    """Thin wrapper around bedrock-runtime for this project."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._runtime = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
        )
        self._chat_model_id = settings.bedrock_chat_model_id
        self._embed_model_id = settings.bedrock_embedding_model_id
        self._embed_dimensions = settings.bedrock_embedding_dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Titan Text Embeddings V2: one InvokeModel call per input string."""
        out: list[list[float]] = []
        for t in texts:
            body = json.dumps(
                {
                    "inputText": t,
                    "dimensions": self._embed_dimensions,
                    "embeddingTypes": ["float"],
                }
            )
            resp = self._runtime.invoke_model(
                modelId=self._embed_model_id,
                body=body,
                accept="application/json",
                contentType="application/json",
            )
            raw = json.loads(resp["body"].read())
            vec = self._parse_titan_embedding(raw)
            out.append(vec)
        return out

    @staticmethod
    def _parse_titan_embedding(raw: dict) -> list[float]:
        if "embedding" in raw and raw["embedding"]:
            return list(raw["embedding"])
        by_type = raw.get("embeddingsByType") or {}
        floats = by_type.get("float")
        if floats:
            return list(floats)
        raise ValueError("Titan embedding response missing float vector")

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        """Run Claude on Bedrock; prefer Converse, fall back to InvokeModel."""
        try:
            return self._chat_via_converse(
                system, user, temperature=temperature, max_tokens=max_tokens
            )
        except ClientError as e:
            err_code = e.response.get("Error", {}).get("Code", "")
            if err_code == "AccessDeniedException":
                raise
            log.warning("Bedrock Converse failed (%s), trying InvokeModel: %s", err_code, e)
        except Exception as e:
            log.warning("Bedrock Converse failed, trying InvokeModel: %s", e)
        return self._chat_via_invoke(system, user, temperature=temperature, max_tokens=max_tokens)

    def _chat_via_converse(
        self,
        system: str,
        user: str,
        *,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        inference: dict = {
            "temperature": temperature,
            "maxTokens": max_tokens if max_tokens is not None else 4096,
        }
        response = self._runtime.converse(
            modelId=self._chat_model_id,
            messages=[{"role": "user", "content": [{"text": user}]}],
            system=[{"text": system}],
            inferenceConfig=inference,
        )
        msg = response.get("output", {}).get("message", {})
        content = msg.get("content") or []
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "".join(parts).strip()

    def _chat_via_invoke(
        self,
        system: str,
        user: str,
        *,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens if max_tokens is not None else 4096,
                "temperature": temperature,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
        )
        resp = self._runtime.invoke_model(
            modelId=self._chat_model_id,
            body=body,
            accept="application/json",
            contentType="application/json",
        )
        raw = json.loads(resp["body"].read())
        content = raw.get("content") or []
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts).strip()
