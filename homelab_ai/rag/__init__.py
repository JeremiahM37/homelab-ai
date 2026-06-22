"""Optional document RAG — ChromaDB + an embedding model, with hybrid
(dense + BM25) retrieval, optional LLM rerank, incremental indexing, and
visibility tiers.

Lazy-import only when `features.rag.enabled` is true. Requires:

    pip install homelab-ai[rag]    # adds chromadb (+ rank_bm25 for hybrid)

Provides:
- `RAGStore` for ingestion + hybrid search
- `make_llm_reranker` to build an optional rerank pass from an LLM client
- tier helpers (`allowed_tiers`, `tiers_for_surface`)
- `/api/rag/*` endpoints (only registered when the feature is on)
"""
from .rerank import make_llm_reranker
from .store import RAGStore
from .tiers import TIERS, allowed_tiers, tiers_for_surface

__all__ = ["RAGStore", "make_llm_reranker", "TIERS",
           "allowed_tiers", "tiers_for_surface"]
