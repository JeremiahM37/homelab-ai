"""Optional document RAG — uses ChromaDB + an embedding model.

Lazy-import only when `features.rag.enabled` is true. Requires:

    pip install homelab-ai[rag]    # adds chromadb

Provides:
- `RAGStore` for ingestion + similarity search
- `/api/rag/ingest` and `/api/rag/ask` endpoints (only registered when on)
"""
from .store import RAGStore

__all__ = ["RAGStore"]
