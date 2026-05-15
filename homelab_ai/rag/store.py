"""ChromaDB-backed vector store for document RAG.

The chromadb import is lazy — happens only when a RAGStore is instantiated.
A user without `pip install homelab-ai[rag]` can still import the package;
they only hit the missing-dep error if they actually enable the feature.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger("homelab_ai.rag")


def _chunk(text: str, size: int, overlap: int) -> list[str]:
    """Simple character-based chunking. Good enough for most prose."""
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks = []
    i = 0
    step = max(1, size - overlap)
    while i < len(text):
        chunks.append(text[i:i + size])
        i += step
    return chunks


class RAGStore:
    def __init__(self, chroma_path: str | Path,
                 embedder, chunk_size: int = 800, chunk_overlap: int = 100):
        self.path = Path(chroma_path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Lazy import — only happens when the feature is actually used.
        try:
            import chromadb
        except ImportError as e:
            raise ImportError(
                "features.rag is enabled but `chromadb` is not installed. "
                "Run: pip install homelab-ai[rag]"
            ) from e
        self._client = chromadb.PersistentClient(path=str(self.path))
        self._collection = self._client.get_or_create_collection("homelab_ai")

    @staticmethod
    def _doc_id(source: str, idx: int) -> str:
        return hashlib.sha1(f"{source}#{idx}".encode()).hexdigest()[:24]

    async def ingest(self, source: str, text: str,
                     metadata: dict | None = None) -> dict:
        """Chunk + embed + store. `source` is a stable identifier (URL,
        path, document ID) so re-ingesting is idempotent."""
        chunks = _chunk(text, self.chunk_size, self.chunk_overlap)
        if not chunks:
            return {"chunks": 0}

        ids = [self._doc_id(source, i) for i in range(len(chunks))]
        embeddings = [await self.embedder(c) for c in chunks]
        metadatas = [{**(metadata or {}), "source": source, "chunk": i}
                     for i in range(len(chunks))]
        self._collection.upsert(
            ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas,
        )
        return {"chunks": len(chunks), "source": source}

    async def search(self, query: str, k: int = 5,
                     source: str | None = None) -> list[dict]:
        emb = await self.embedder(query)
        where = {"source": source} if source else None
        res = self._collection.query(
            query_embeddings=[emb], n_results=k, where=where,
        )
        out = []
        if not res.get("documents"):
            return out
        docs = res["documents"][0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for d, m, dist in zip(docs, metas, dists, strict=False):
            out.append({
                "text": d,
                "source": (m or {}).get("source"),
                "chunk": (m or {}).get("chunk"),
                "distance": dist,
            })
        return out

    def delete_source(self, source: str) -> int:
        self._collection.delete(where={"source": source})
        return 1

    def stats(self) -> dict:
        return {"chunks": self._collection.count()}
