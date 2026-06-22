"""Tests for the RAG feature: tiers, chunking, fusion/BM25, manifest, and an
end-to-end store roundtrip (skipped without chromadb)."""
import pytest

from homelab_ai.rag.fusion import BM25Index, rrf, tokenize
from homelab_ai.rag.manifest import Manifest, content_hash
from homelab_ai.rag.text import chunk
from homelab_ai.rag.tiers import allowed_tiers, normalize_tier, tiers_for_surface


# ── tiers ──────────────────────────────────────────────────────────────────
def test_allowed_tiers_monotonic():
    assert allowed_tiers("admin") == {"public", "lan", "admin"}
    assert allowed_tiers("lan") == {"public", "lan"}
    assert allowed_tiers("public") == {"public"}


def test_surface_caps_keep_personal_off_public():
    assert tiers_for_surface("discord") == {"public"}
    assert "admin" not in tiers_for_surface("discord")
    assert tiers_for_surface("api") == {"public", "lan", "admin"}
    # override wins
    assert tiers_for_surface("discord", {"discord": "lan"}) == {"public", "lan"}


def test_normalize_tier_defaults():
    assert normalize_tier(None) == "lan"
    assert normalize_tier("bogus", default="public") == "public"
    assert normalize_tier("admin") == "admin"


# ── chunking ───────────────────────────────────────────────────────────────
def test_chunk_packs_and_splits():
    text = "# H1\n" + ("word " * 300) + "\n\n## H2\n" + ("x" * 2000)
    chunks = chunk(text, size=800, overlap=100)
    assert len(chunks) >= 2
    assert all(len(c) <= 1000 for c in chunks)


def test_chunk_empty():
    assert chunk("") == []
    assert chunk("   ") == []


# ── fusion ─────────────────────────────────────────────────────────────────
def test_rrf_prefers_items_high_in_both():
    a = [{"id": "1"}, {"id": "2"}]
    b = [{"id": "2"}, {"id": "3"}]
    ids = [h["id"] for h in rrf(a, b)]
    assert ids[0] == "2"
    assert set(ids) == {"1", "2", "3"}


def test_tokenize():
    assert tokenize("Gluetun-NetNS, qBittorrent!") == [
        "gluetun", "netns", "qbittorrent"]


def test_bm25_keyword_match():
    pytest.importorskip("rank_bm25")
    idx = BM25Index()
    # Several docs so the matched term has positive IDF (BM25Okapi gives a
    # term appearing in ~half a tiny corpus a zero IDF).
    rows = [
        {"id": "a", "text": "the cat sat on the mat", "metadata": {"tier": "lan"}},
        {"id": "b", "text": "docker compose gluetun vpn tunnel", "metadata": {"tier": "lan"}},
        {"id": "c", "text": "weather forecast sunny skies", "metadata": {"tier": "lan"}},
        {"id": "d", "text": "grocery list milk eggs bread", "metadata": {"tier": "lan"}},
        {"id": "e", "text": "python asyncio tutorial notes", "metadata": {"tier": "lan"}},
    ]
    assert idx.build(rows, fingerprint=5)
    hits = idx.search("gluetun vpn", k=3)
    assert hits and hits[0]["id"] == "b"


def test_bm25_allow_filter():
    pytest.importorskip("rank_bm25")
    idx = BM25Index()
    rows = [
        {"id": "pub", "text": "quarterly report summary", "metadata": {"tier": "public"}},
        {"id": "sec", "text": "quarterly report secret", "metadata": {"tier": "admin"}},
        {"id": "f1", "text": "unrelated cat content", "metadata": {"tier": "lan"}},
        {"id": "f2", "text": "unrelated dog content", "metadata": {"tier": "lan"}},
        {"id": "f3", "text": "unrelated bird content", "metadata": {"tier": "lan"}},
    ]
    idx.build(rows, fingerprint=5)
    hits = idx.search("quarterly report", k=5,
                      allow=lambda m: m.get("tier") == "public")
    assert {h["id"] for h in hits} == {"pub"}


# ── manifest ───────────────────────────────────────────────────────────────
def test_manifest_incremental(tmp_path):
    m = Manifest(tmp_path / "m.db")
    h1 = content_hash("hello", {"a": 1})
    assert not m.unchanged("s1", h1)
    m.record("s1", h1, 3, "lan")
    assert m.unchanged("s1", h1)
    assert m.n_chunks("s1") == 3
    # content change -> not unchanged
    assert not m.unchanged("s1", content_hash("hello world", {"a": 1}))
    m.forget("s1")
    assert not m.unchanged("s1", h1)


# ── store roundtrip (needs chromadb) ───────────────────────────────────────
@pytest.mark.asyncio
async def test_store_roundtrip_and_tier_gating(tmp_path):
    pytest.importorskip("chromadb")
    from homelab_ai.rag import RAGStore

    async def fake_embed(text: str):
        # deterministic tiny embedding from token hashing
        v = [0.0] * 16
        for t in tokenize(text):
            v[hash(t) % 16] += 1.0
        return v

    store = RAGStore(tmp_path / "chroma", fake_embed, chunk_size=200, hybrid=True)

    # incremental: second ingest of identical content is skipped
    r1 = await store.ingest("doc-pub", "public gluetun vpn notes", tier="public")
    assert r1["chunks"] >= 1
    r2 = await store.ingest("doc-pub", "public gluetun vpn notes", tier="public")
    assert r2.get("skipped") is True
    await store.ingest("doc-sec", "secret admin gluetun credentials", tier="admin")

    # admin surface sees both; public surface must not see admin content
    admin_hits = await store.search("gluetun", k=5, max_tier="admin")
    assert any(h["source"] == "doc-sec" for h in admin_hits)
    pub_hits = await store.search("gluetun", k=5, max_tier="public")
    assert pub_hits and all(h["tier"] == "public" for h in pub_hits)
    assert all(h["source"] != "doc-sec" for h in pub_hits)
