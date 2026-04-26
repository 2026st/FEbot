#!/usr/bin/env python3
"""Migrate existing corpus data from local files to Supabase."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openai import OpenAI  # noqa: E402

from febot.config import Settings  # noqa: E402
from febot.supabase_storage import SupabaseStorage  # noqa: E402

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120


def _chunk_text(text: str) -> list[str]:
    """Chunk text into overlapping segments."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    chunks: list[str] = []
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
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def main() -> None:
    """Migrate corpus documents and embeddings to Supabase."""
    settings = Settings.load(require_slack=False)

    if not settings.rag_enabled():
        raise SystemExit("AI_API_KEY が設定されていないため、埋め込み（migrate）は実行できません。")

    if not settings.use_supabase:
        raise SystemExit(
            "Supabase設定が見つかりません。.envファイルに SUPABASE_URL と SUPABASE_KEY を設定してください。"
        )

    if not settings.corpus_dir.is_dir():
        raise SystemExit(f"CORPUS_DIR not found: {settings.corpus_dir}")

    md_files = sorted(settings.corpus_dir.glob("*.md"))
    if not md_files:
        raise SystemExit("No .md files in corpus directory")

    print(f"Found {len(md_files)} markdown files in {settings.corpus_dir}")

    # Initialize clients
    oai = OpenAI(api_key=settings.ai_api_key, base_url=settings.ai_base_url)
    storage = SupabaseStorage(settings.supabase_url, settings.supabase_key)

    total_chunks = 0

    for idx, path in enumerate(md_files, 1):
        print(f"[{idx}/{len(md_files)}] Processing: {path.name}")

        # Read file content
        content = path.read_text(encoding="utf-8")

        # Save document to Supabase
        doc_id = storage.upsert_document(path.name, content)

        # Chunk the text
        chunks = _chunk_text(content)
        if not chunks:
            print(f"  [WARN] No chunks generated for {path.name}, skipping")
            continue

        print(f"  Generated {len(chunks)} chunks")

        # Generate embeddings in batches
        batch_size = 64
        embeddings: list[list[float]] = []

        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i : i + batch_size]
            resp = oai.embeddings.create(model=settings.ai_embedding_model, input=batch_chunks)
            ordered = sorted(resp.data, key=lambda x: x.index)
            embeddings.extend(item.embedding for item in ordered)
            print(f"  Embedded chunks {i + 1}-{min(i + batch_size, len(chunks))}/{len(chunks)}")

        # Save chunks with embeddings to Supabase
        chunk_tuples = list(zip(chunks, embeddings))
        storage.upsert_chunks(doc_id, path.name, chunk_tuples)

        total_chunks += len(chunks)
        print(f"  [OK] Saved {len(chunks)} chunks for {path.name}")

    print("\n[SUCCESS] Migration complete!")
    print(f"  Total documents: {len(md_files)}")
    print(f"  Total chunks: {total_chunks}")

    # Verify the migration
    doc_count = storage.count_documents()
    chunk_count = storage.count_chunks()
    print("\nSupabase verification:")
    print(f"  Documents in DB: {doc_count}")
    print(f"  Chunks in DB: {chunk_count}")


if __name__ == "__main__":
    main()
