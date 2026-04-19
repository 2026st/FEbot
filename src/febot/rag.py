"""Retrieve from Chroma and answer with OpenAI-compatible chat API."""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

import chromadb
from openai import OpenAI

from febot.config import Settings

COLLECTION = "febot_corpus"
GLOSSARY_FILE = "glossary.md"

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120

SYSTEM_PROMPT = """あなたは基本情報技術者試験（FE）の学習支援ボットです。
与えられた【参照抜粋】のみを根拠に、簡潔に日本語で答えてください。
参照抜粋に質問への答えが含まれない場合は推測せず、「この質問に答える記述は参照抜粋にありません」と述べてください。
「glossary.md（用語マッチ）」の節があるときは、用語説明の質問ではそれを最優先の根拠にしてください。
試験の正式な出題やIPA公式の解釈を断定しないでください。
【出典】には、回答で実際に根拠としたファイル名だけを箇条書きにしてください。根拠に使っていないファイルは書かないでください。根拠が参照抜粋にない場合は【出典】に「なし」とだけ書いてください。"""


@dataclass
class RagAnswer:
    text: str
    sources: list[str]


def _chunk_text(text: str, source: str) -> list[tuple[str, dict[str, str]]]:
    """Chunk text into overlapping segments. Same logic as scripts/ingest.py."""
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


def _load_glossary_sections(corpus_dir: Path) -> list[tuple[str, str]]:
    """(見出しタイトル, 節全文) のリスト。"""
    path = corpus_dir / GLOSSARY_FILE
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"^### (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        sections.append((title, block))
    return sections


def _question_tokens(question: str) -> set[str]:
    toks: set[str] = set()
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9+./-]*", question):
        toks.add(m.group(0).casefold())
    for m in re.finditer(r"[\u3040-\u30ff\u4e00-\u9fff]{2,}", question):
        toks.add(m.group(0))
    return toks


def _section_matches_tokens(section_text: str, tokens: set[str]) -> bool:
    st = section_text.casefold()
    for tok in tokens:
        if len(tok) <= 1:
            continue
        if re.fullmatch(r"[a-z0-9+./-]+", tok):
            if len(tok) >= 3:
                if tok in st:
                    return True
            elif re.search(r"(?<![a-z0-9+./-])" + re.escape(tok) + r"(?![a-z0-9+./-])", st):
                return True
        elif tok in section_text:
            return True
    return False


def _glossary_boost(
    question: str, sections: list[tuple[str, str]], *, max_sections: int = 2
) -> list[str]:
    if not sections:
        return []
    tokens = _question_tokens(question)
    if not tokens:
        return []
    out: list[str] = []
    for _title, block in sections:
        if _section_matches_tokens(block, tokens):
            excerpt = block if len(block) <= 1400 else block[:1400] + "…"
            out.append(excerpt)
            if len(out) >= max_sections:
                break
    return out


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
        self._oai = OpenAI(api_key=settings.ai_api_key, base_url=settings.ai_base_url)
        self._chroma = chromadb.PersistentClient(path=str(settings.chroma_path))
        self._collection = self._chroma.get_collection(COLLECTION)
        self.limiter = RateLimiter(settings.rate_limit_per_minute)
        self._glossary_sections = _load_glossary_sections(settings.corpus_dir)

    def answer(self, user_id: str, question: str) -> RagAnswer | None:
        """Answer from corpus. Returns None if no relevant knowledge found (triggers web search fallback)."""
        if not self.limiter.allow(user_id):
            return RagAnswer(
                text="利用が集中しています。1分ほど待ってから再度お試しください。",
                sources=[],
            )

        q_emb = self._oai.embeddings.create(
            model=self._settings.ai_embedding_model,
            input=[question],
        )
        query_vector = q_emb.data[0].embedding

        n_docs = self._collection.count()
        if n_docs == 0:
            return RagAnswer(
                text="コーパスが空です。`python3 scripts/ingest.py` を実行してください。",
                sources=[],
            )

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
        picked: list[tuple[str, str, dict]] = []
        for doc, meta, dist in zip(
            docs,
            metas,
            dists if use_dist else [0.0] * len(docs),
            strict=True,
        ):
            if use_dist and dist > max_d:
                continue
            src = (meta or {}).get("source") or "unknown"
            picked.append((doc, src, meta or {}))
            if len(picked) >= self._settings.rag_top_k:
                break

        gloss_excerpts = _glossary_boost(question, self._glossary_sections)

        # No knowledge found: neither vector results nor glossary match passed threshold
        if not picked and not gloss_excerpts:
            return None

        parts: list[str] = []
        source_names: list[str] = []

        for gex in gloss_excerpts:
            label = f"{GLOSSARY_FILE}（用語マッチ）"
            parts.append(f"### {label}\n{gex}")
            if label not in source_names:
                source_names.append(label)

        vec_cap = (
            self._settings.rag_top_k
            if not gloss_excerpts
            else max(1, min(4, self._settings.rag_top_k))
        )
        for doc, src, _meta in picked[:vec_cap]:
            excerpt = doc.strip() if doc else ""
            if len(excerpt) > 700:
                excerpt = excerpt[:700] + "…"
            parts.append(f"### {src}\n{excerpt}")
            if src not in source_names:
                source_names.append(src)

        context = "\n\n".join(parts) if parts else "（参照なし）"

        user_content = f"【ユーザーの質問】\n{question}\n\n【参照抜粋】\n{context}"

        chat = self._oai.chat.completions.create(
            model=self._settings.ai_chat_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
        )
        text = (chat.choices[0].message.content or "").strip()
        # LLM explicitly said the corpus has no relevant info → fall through to web search
        if "参照抜粋にありません" in text:
            return None
        return RagAnswer(text=text, sources=source_names)

    def add_to_corpus(self, content: str, source_name: str) -> None:
        """Chunk, embed, and upsert into Chroma. Also saves file to corpus dir."""
        file_path = self._settings.corpus_dir / source_name
        file_path.write_text(content, encoding="utf-8")

        chunks = _chunk_text(content, source_name)
        if not chunks:
            return

        texts = [c[0] for c in chunks]
        metas = [c[1] for c in chunks]

        resp = self._oai.embeddings.create(
            model=self._settings.ai_embedding_model,
            input=texts,
        )
        embeddings = [e.embedding for e in sorted(resp.data, key=lambda x: x.index)]

        ids = []
        for i, (text, meta) in enumerate(zip(texts, metas, strict=True)):
            src = meta["source"]
            h = hashlib.sha256(f"{src}:{i}:{text[:80]}".encode()).hexdigest()[:24]
            ids.append(f"{src}_{i}_{h}")
        # Use upsert so repeated identical questions don't cause duplicate-ID errors
        self._collection.upsert(ids=ids, documents=texts, metadatas=metas, embeddings=embeddings)
