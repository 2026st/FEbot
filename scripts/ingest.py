#!/usr/bin/env python3
"""Chunk corpus Markdown, embed with OpenAI-compatible API, persist Chroma."""

from __future__ import annotations

import contextlib
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openai import OpenAI  # noqa: E402

from febot.config import Settings  # noqa: E402
from febot.rag import COLLECTION  # noqa: E402

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120


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


def main() -> None:
    import chromadb

    settings = Settings.load(require_slack=False)
    if not settings.rag_enabled():
        raise SystemExit("AI_API_KEY が設定されていないため、埋め込み（ingest）は実行できません。")
    if not settings.corpus_dir.is_dir():
        raise SystemExit(f"CORPUS_DIR not found: {settings.corpus_dir}")

    md_files = sorted(settings.corpus_dir.glob("*.md"))
    if not md_files:
        raise SystemExit("No .md files in corpus directory")

    all_chunks: list[tuple[str, dict[str, str]]] = []
    for path in md_files:
        chunks = _chunk_text(path.read_text(encoding="utf-8"), path.name)
        all_chunks.extend(chunks)

    if not all_chunks:
        raise SystemExit("No chunks produced")

    client = OpenAI(api_key=settings.ai_api_key, base_url=settings.ai_base_url)
    texts = [c[0] for c in all_chunks]
    metas = [c[1] for c in all_chunks]

    batch = 64
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch):
        batch_texts = texts[i : i + batch]
        resp = client.embeddings.create(model=settings.ai_embedding_model, input=batch_texts)
        ordered = sorted(resp.data, key=lambda x: x.index)
        embeddings.extend(item.embedding for item in ordered)

    settings.chroma_path.parent.mkdir(parents=True, exist_ok=True)
    chroma = chromadb.PersistentClient(path=str(settings.chroma_path))
    with contextlib.suppress(Exception):
        chroma.delete_collection(COLLECTION)
    coll = chroma.get_or_create_collection(name=COLLECTION, metadata={"hnsw:space": "cosine"})

    ids = []
    for i, (doc, meta) in enumerate(zip(texts, metas, strict=True)):
        h = hashlib.sha256(f"{meta['source']}:{i}:{doc[:80]}".encode()).hexdigest()[:24]
        ids.append(f"{meta['source']}_{i}_{h}")

    coll.add(ids=ids, documents=texts, metadatas=metas, embeddings=embeddings)
    print(f"Ingested {len(ids)} chunks into {settings.chroma_path} (collection={COLLECTION})")


if __name__ == "__main__":
    main()
