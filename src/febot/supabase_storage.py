"""Supabase storage layer for corpus documents and vector search."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from supabase import Client, create_client

log = logging.getLogger(__name__)


class SupabaseStorage:
    """Handles corpus document storage and vector search using Supabase."""

    def __init__(self, url: str, key: str) -> None:
        """Initialize Supabase client.

        Args:
            url: Supabase project URL
            key: Supabase API key (anon/public key)
        """
        self.client: Client = create_client(url, key)

    def upsert_document(self, source_name: str, content: str) -> str:
        """Save or update a corpus document.

        Args:
            source_name: Unique identifier for the document (filename)
            content: Full markdown content

        Returns:
            Document ID (UUID)
        """
        try:
            # Check if document already exists
            result = (
                self.client.table("corpus_documents")
                .select("id")
                .eq("source_name", source_name)
                .execute()
            )

            if result.data:
                # Update existing document
                doc_id = result.data[0]["id"]
                self.client.table("corpus_documents").update(
                    {"content": content, "source_name": source_name}
                ).eq("id", doc_id).execute()
                log.info("Updated document: %s (id=%s)", source_name, doc_id)
                return doc_id
            else:
                # Insert new document
                result = (
                    self.client.table("corpus_documents")
                    .insert({"source_name": source_name, "content": content})
                    .execute()
                )
                doc_id = result.data[0]["id"]
                log.info("Inserted new document: %s (id=%s)", source_name, doc_id)
                return doc_id

        except Exception as e:
            log.error("Failed to upsert document %s: %s", source_name, e)
            raise

    def upsert_chunks(
        self,
        document_id: str,
        source_name: str,
        chunks: list[tuple[str, list[float]]],
    ) -> None:
        """Save or update document chunks with embeddings.

        Args:
            document_id: UUID of the parent document
            source_name: Source filename for reference
            chunks: List of (text, embedding_vector) tuples
        """
        try:
            # Delete existing chunks for this document
            self.client.table("corpus_chunks").delete().eq("document_id", document_id).execute()

            # Insert new chunks
            chunk_records = []
            for i, (text, embedding) in enumerate(chunks):
                chunk_records.append(
                    {
                        "document_id": document_id,
                        "chunk_index": i,
                        "content": text,
                        "embedding": embedding,
                        "source_name": source_name,
                    }
                )

            if chunk_records:
                self.client.table("corpus_chunks").insert(chunk_records).execute()
                log.info("Inserted %d chunks for document %s", len(chunk_records), document_id)

        except Exception as e:
            log.error("Failed to upsert chunks for document %s: %s", document_id, e)
            raise

    def vector_search(
        self, query_embedding: list[float], top_k: int = 5, max_distance: float | None = None
    ) -> list[dict[str, Any]]:
        """Perform vector similarity search.

        Args:
            query_embedding: Query vector (1536 dimensions for text-embedding-3-small)
            top_k: Number of results to return
            max_distance: Optional maximum cosine distance threshold

        Returns:
            List of dicts with keys: content, source_name, distance
        """
        try:
            # Use Supabase RPC for vector search
            # Note: We need to create this RPC function in Supabase
            result = self.client.rpc(
                "match_corpus_chunks",
                {
                    "query_embedding": query_embedding,
                    "match_count": top_k,
                    "max_distance": max_distance if max_distance is not None else 1.0,
                },
            ).execute()

            return result.data if result.data else []

        except Exception as e:
            log.error("Vector search failed: %s", e)
            raise

    def get_document_by_source(self, source_name: str) -> dict[str, Any] | None:
        """Retrieve a document by its source name.

        Args:
            source_name: Unique filename identifier

        Returns:
            Document dict or None if not found
        """
        try:
            result = (
                self.client.table("corpus_documents")
                .select("*")
                .eq("source_name", source_name)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            log.error("Failed to get document %s: %s", source_name, e)
            return None

    def count_documents(self) -> int:
        """Count total number of corpus documents.

        Returns:
            Document count
        """
        try:
            result = (
                self.client.table("corpus_documents")
                .select("id", count="exact")
                .execute()
            )
            return result.count if result.count is not None else 0
        except Exception as e:
            log.error("Failed to count documents: %s", e)
            return 0

    def count_chunks(self) -> int:
        """Count total number of corpus chunks.

        Returns:
            Chunk count
        """
        try:
            result = (
                self.client.table("corpus_chunks")
                .select("id", count="exact")
                .execute()
            )
            return result.count if result.count is not None else 0
        except Exception as e:
            log.error("Failed to count chunks: %s", e)
            return 0
