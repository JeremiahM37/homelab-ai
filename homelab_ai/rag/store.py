"""ChromaDB-backed vector store for document RAG.

Retrieval is hybrid: dense vectors + BM25 keyword search fused with RRF, then an
optional LLM rerank. Indexing is incremental (a content-hash manifest skips
unchanged sources and prunes stale chunks). Every chunk carries a visibility
tier so a capped query never sees content above its level.

The chromadb import is lazy — happens only when a RAGStore is instantiated, so a
user without `pip install homelab-ai[rag]` can still import the package.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .fusion import BM25Index, rrf
from .manifest import Manifest, content_hash
from .rerank import Reranker
from .text import chunk as _chunk
from .tiers import allowed_tiers, normalize_tier, tiers_for_surface

logger = logging.getLogger("homelab_ai.rag")


class RAGStore:
    def __init__(self, chroma_path: str | Path, embedder, chunk_size: int = 800,
                 chunk_overlap: int = 100, *, hybrid: bool = True,
                 candidate_k: int = 24, default_tier: str = "lan",
                 reranker: Reranker | None = None,
                 surface_tiers: dict | None = None):
        self.path = Path(chroma_path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.hybrid = hybrid
        self.candidate_k = candidate_k
        self.default_tier = normalize_tier(default_tier)
        self.reranker = reranker
        self.surface_tiers = surface_tiers or {}

        try:
            import chromadb
        except ImportError as e:
            raise ImportError(
                "features.rag is enabled but `chromadb` is not installed. "
                "Run: pip install homelab-ai[rag]"
            ) from e
        self._client = chromadb.PersistentClient(path=str(self.path))
        self._collection = self._client.get_or_create_collection(
            "homelab_ai", metadata={"hnsw:space": "cosine"})
        self._manifest = Manifest(self.path / "manifest.db")
        self._bm25 = BM25Index()
        self._bm25_count = -1

    # ── ingestion (incremental) ───────────────────────────────────────────
    async def ingest(self, source: str, text: str, metadata: dict | None = None,
                     tier: str | None = None) -> dict:
        """Chunk + embed + store. Idempotent by `source`: re-ingesting identical
        content is a no-op; changed content replaces the source's prior chunks."""
        tier = normalize_tier(tier or self.default_tier)
        chash = content_hash(text, metadata)
        if self._manifest.unchanged(source, chash):
            return {"source": source, "chunks": self._manifest.n_chunks(source),
                    "skipped": True}

        # Replace any prior version of this source.
        self._collection.delete(where={"source": source})
        chunks = _chunk(text, self.chunk_size, self.chunk_overlap)
        if not chunks:
            self._manifest.record(source, chash, 0, tier)
            return {"source": source, "chunks": 0}

        ids = [f"{source}::{i}" for i in range(len(chunks))]
        embeddings = [await self.embedder(c) for c in chunks]
        metadatas = [{**(metadata or {}), "source": source, "tier": tier, "chunk": i}
                     for i in range(len(chunks))]
        self._collection.add(ids=ids, documents=chunks, embeddings=embeddings,
                             metadatas=metadatas)
        self._manifest.record(source, chash, len(chunks), tier)
        return {"source": source, "chunks": len(chunks), "tier": tier}

    # ── retrieval (hybrid + rerank, tier-gated) ───────────────────────────
    async def search(self, query: str, k: int = 5, source: str | None = None,
                     max_tier: str = "admin", surface: str | None = None) -> list[dict]:
        tiers = (tiers_for_surface(surface, self.surface_tiers)
                 if surface else allowed_tiers(max_tier))
        where = self._where(source, tiers)

        emb = await self.embedder(query)
        res = self._collection.query(query_embeddings=[emb],
                                     n_results=self.candidate_k, where=where)
        dense = self._dense_rows(res)

        fused = dense
        if self.hybrid:
            self._refresh_bm25()
            kw = self._bm25.search(
                query, self.candidate_k,
                allow=lambda m: m.get("tier") in tiers and (
                    source is None or m.get("source") == source))
            if kw:
                fused = rrf(dense, kw)

        if self.reranker and len(fused) > k:
            order = await self.reranker(query, [h["text"] for h in fused], k)
            fused = [fused[i] for i in order]

        return [self._public(h) for h in fused[:k]]

    def delete_source(self, source: str) -> int:
        self._collection.delete(where={"source": source})
        self._manifest.forget(source)
        return 1

    def stats(self) -> dict:
        return {"chunks": self._collection.count(), **self._manifest.stats(),
                "hybrid": self.hybrid, "rerank": self.reranker is not None}

    # ── helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _where(source: str | None, tiers: set[str]):
        clauses = [{"tier": {"$in": list(tiers)}}]
        if source:
            clauses.append({"source": source})
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    @staticmethod
    def _dense_rows(res) -> list[dict]:
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        rows = []
        for i in range(len(ids)):
            rows.append({"id": ids[i], "text": docs[i],
                         "metadata": metas[i] or {},
                         "distance": dists[i] if i < len(dists) else None})
        return rows

    @staticmethod
    def _public(h: dict) -> dict:
        m = h.get("metadata") or {}
        return {"text": h["text"], "source": m.get("source"),
                "chunk": m.get("chunk"), "tier": m.get("tier"),
                "distance": h.get("distance")}

    def _refresh_bm25(self) -> None:
        n = self._collection.count()
        if self._bm25.available and n == self._bm25_count:
            return
        res = self._collection.get(include=["documents", "metadatas"])
        ids = res.get("ids") or []
        rows = [{"id": ids[i], "text": (res["documents"] or [])[i],
                 "metadata": (res["metadatas"] or [])[i] or {}}
                for i in range(len(ids))]
        self._bm25.build(rows, fingerprint=n)
        self._bm25_count = n
