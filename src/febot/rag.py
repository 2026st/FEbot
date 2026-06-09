"""Retrieve from Chroma/Supabase and answer via Bedrock or OpenAI-compatible API."""

from __future__ import annotations

import hashlib
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass

import chromadb

from febot.config import Settings
from febot.llm_backend import get_llm_backend
from febot.slack_format import SLACK_OUTPUT_RULES
from febot.supabase_storage import SupabaseStorage
from febot.thread_session import ChatTurn, build_user_content_with_history, embed_query_text
from febot.web_search import urls_from_web_cache_content

COLLECTION = "febot_corpus"

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120

SYSTEM_PROMPT = (
    """あなたは基本情報技術者試験（FE）の学習支援ボットです。
与えられた【参照抜粋】のみを根拠に、初学者でも分かるように丁寧に日本語で答えてください。
参照抜粋に質問への答えが含まれない場合は推測せず、「この質問に答える記述は参照抜粋にありません」と述べてください。
「glossary.md（用語マッチ）」の節があるときは、用語説明の質問ではそれを最優先の根拠にしてください。
試験の正式な出題やIPA公式の解釈を断定しないでください。

"""
    + SLACK_OUTPUT_RULES
)

_EMPTY_VECTOR_MSG = (
    "ベクトルストアにデータがありません。管理者にベクトル DB の投入を依頼してください。"
)


@dataclass
class RagAnswer:
    text: str
    sources: list[str]


def build_rag_user_content(
    question: str,
    context: str,
    history: list[ChatTurn] | None = None,
) -> str:
    return build_user_content_with_history(
        question=question,
        context=context,
        history=history,
    )


def _chunk_text(text: str, source: str) -> list[tuple[str, dict[str, str]]]:
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    chunks: list[tuple[str, dict[str, str]]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + CHUNK_SIZE, n)
        piece = text[start:end]
        if end < n:
            cut = piece.rfind("\n\n")
            if cut > CHUNK_SIZE // 2:
                piece = piece[:cut]
                end = start + cut
        piece = piece.strip()
        if piece:
            chunks.append((piece, {"source": source}))
        if end >= n:
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def _rag_max_distance() -> float | None:
    """Chroma の cosine 空間では距離は小さいほど近い（目安: 1 - cosine_similarity）。"""
    raw = os.environ.get("RAG_MAX_DISTANCE", "0.52").strip()
    if raw.lower() in ("", "off", "none"):
        return None
    return float(raw)


def _rag_pool_size(top_k: int) -> int:
    mult = int(os.environ.get("RAG_POOL_MULT", "5"))
    return max(24, top_k * mult)


class RateLimiter:
    """Very small in-memory limiter per Slack user id (PoC)."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, user_id: str) -> bool:
        now = time.monotonic()
        q = self._hits[user_id]
        window = 60.0
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= self.per_minute:
            return False
        q.append(now)
        return True


class RagEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.llm = get_llm_backend(settings)

        if settings.use_supabase:
            self._storage = SupabaseStorage(settings.supabase_url, settings.supabase_key)
            self._chroma = None
            self._collection = None
        else:
            self._storage = None
            self._chroma = chromadb.PersistentClient(path=str(settings.chroma_path))
            self._collection = self._chroma.get_collection(COLLECTION)

        self.limiter = RateLimiter(settings.rate_limit_per_minute)

    def answer(
        self,
        user_id: str,
        question: str,
        *,
        history: list[ChatTurn] | None = None,
    ) -> RagAnswer | None:
        """Answer from vector store. Returns None if no relevant knowledge (web search fallback)."""
        if not self.limiter.allow(user_id):
            return RagAnswer(
                text="利用が集中しています。1分ほど待ってから再度お試しください。",
                sources=[],
            )

        embed_text = embed_query_text(question, history)
        query_vector = self.llm.embed_texts([embed_text])[0]

        if self._storage:
            n_docs = self._storage.count_chunks()
            if n_docs == 0:
                return RagAnswer(text=_EMPTY_VECTOR_MSG, sources=[])

            pool = _rag_pool_size(self._settings.rag_top_k)
            max_d = _rag_max_distance()
            results = self._storage.vector_search(query_vector, top_k=pool, max_distance=max_d)

            picked: list[tuple[str, str, dict]] = []
            for r in results:
                doc = r.get("content", "")
                src = r.get("source_name", "unknown")
                picked.append((doc, src, {}))
                if len(picked) >= self._settings.rag_top_k:
                    break
        else:
            n_docs = self._collection.count()
            if n_docs == 0:
                return RagAnswer(text=_EMPTY_VECTOR_MSG, sources=[])

            pool = _rag_pool_size(self._settings.rag_top_k)
            res = self._collection.query(
                query_embeddings=[query_vector],
                n_results=min(pool, n_docs),
                include=["documents", "metadatas", "distances"],
            )

            docs = (res.get("documents") or [[]])[0] or []
            metas = (res.get("metadatas") or [[]])[0] or []
            dists = (res.get("distances") or [[]])[0] or []

            max_d = _rag_max_distance()
            use_dist = max_d is not None and len(dists) == len(docs)
            picked = []
            for doc, meta, dist in zip(
                docs,
                metas,
                dists if use_dist else [0.0] * len(docs),
            ):
                if use_dist and dist > max_d:
                    continue
                src = (meta or {}).get("source") or "unknown"
                picked.append((doc, src, meta or {}))
                if len(picked) >= self._settings.rag_top_k:
                    break

        if not picked:
            return None

        parts: list[str] = []
        source_names: list[str] = []

        for doc, src, _meta in picked:
            excerpt = doc.strip() if doc else ""
            if len(excerpt) > 700:
                excerpt = excerpt[:700] + "…"
            parts.append(f"### {src}\n{excerpt}")
            if src not in source_names:
                source_names.append(src)

        context = "\n\n".join(parts)

        user_content = build_rag_user_content(question, context, history)

        text = self.llm.chat(
            SYSTEM_PROMPT,
            user_content,
            temperature=0.2,
            max_tokens=None,
        )
        if "参照抜粋にありません" in text:
            return None
        return RagAnswer(text=text, sources=source_names)

    def citation_urls_for_source(self, source_name: str) -> list[str]:
        """Extract citation URLs from a web_cache document stored in Supabase."""
        if not source_name.startswith("web_cache_") or not self._storage:
            return []
        doc = self._storage.get_document_by_source(source_name)
        if not doc:
            return []
        return urls_from_web_cache_content(doc.get("content", ""))

    def add_to_corpus(self, content: str, source_name: str) -> None:
        """Chunk, embed, and upsert into Supabase or Chroma (no local file)."""
        chunks = _chunk_text(content, source_name)
        if not chunks:
            return

        texts = [c[0] for c in chunks]
        embeddings = self.llm.embed_texts(texts)

        if self._storage:
            doc_id = self._storage.upsert_document(source_name, content)
            chunk_tuples = list(zip(texts, embeddings))
            self._storage.upsert_chunks(doc_id, source_name, chunk_tuples)
        else:
            metas = [c[1] for c in chunks]
            ids = []
            for i, (text, meta) in enumerate(zip(texts, metas)):
                src = meta["source"]
                h = hashlib.sha256(f"{src}:{i}:{text[:80]}".encode()).hexdigest()[:24]
                ids.append(f"{src}_{i}_{h}")
            self._collection.upsert(
                ids=ids, documents=texts, metadatas=metas, embeddings=embeddings
            )
