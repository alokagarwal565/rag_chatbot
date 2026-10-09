"""Hybrid retrieval: Chroma HNSW (dense, cosine) + SQLite FTS5 (BM25), fused with Reciprocal Rank Fusion."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.config import settings
from app.providers.base import ScoredChunk


@dataclass
class FusedHit:
    chunk_id: str
    rrf_score: float
    dense_rank: Optional[int] = None
    dense_score: Optional[float] = None
    bm25_rank: Optional[int] = None
    bm25_score: Optional[float] = None


def rrf_fuse(dense: List[Tuple[str, float]], lexical: List[Tuple[str, float]], k: int = 60) -> List[FusedHit]:
    """score(d) = sum over lists of 1 / (k + rank), rank starting at 1. Ties broken by best single rank,
    then chunk id, so the order is deterministic."""
    hits: Dict[str, FusedHit] = {}
    for rank, (cid, score) in enumerate(dense, start=1):
        h = hits.setdefault(cid, FusedHit(cid, 0.0))
        h.rrf_score += 1.0 / (k + rank)
        h.dense_rank, h.dense_score = rank, round(score, 4)
    for rank, (cid, score) in enumerate(lexical, start=1):
        h = hits.setdefault(cid, FusedHit(cid, 0.0))
        h.rrf_score += 1.0 / (k + rank)
        h.bm25_rank, h.bm25_score = rank, round(score, 4)
    best = lambda h: min(r for r in (h.dense_rank, h.bm25_rank) if r is not None)  # noqa: E731
    return sorted(hits.values(), key=lambda h: (-h.rrf_score, best(h), h.chunk_id))


class HybridRetriever:
    def __init__(self, store, vectors, embedder):
        self.store = store
        self.vectors = vectors
        self.embedder = embedder
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lexical")

    def retrieve(self, query: str, doc_ids: Optional[List[str]] = None,
                 dense_k: int = None, lexical_k: int = None) -> Tuple[List[ScoredChunk], Dict[str, float]]:
        dense_k = dense_k or settings.dense_top_k
        lexical_k = lexical_k or settings.lexical_top_k
        timings: Dict[str, float] = {}
        t_all = time.perf_counter()

        def _lexical():
            t = time.perf_counter()
            res = self.store.bm25_search(query, lexical_k, doc_ids)
            return res, (time.perf_counter() - t) * 1000

        lex_future = self._pool.submit(_lexical)  # BM25 runs while the query is embedded and searched

        t = time.perf_counter()
        qvec = self.embedder.embed_query(query)
        timings["embed_ms"] = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        dense = self.vectors.query(qvec, dense_k, doc_ids)
        timings["dense_ms"] = (time.perf_counter() - t) * 1000

        lexical, timings["lexical_ms"] = lex_future.result()

        t = time.perf_counter()
        fused = rrf_fuse(dense, lexical, settings.rrf_k)
        rows = self.store.get_chunks([h.chunk_id for h in fused])
        chunks: List[ScoredChunk] = []
        for h in fused:
            r = rows.get(h.chunk_id)
            if r is None:  # vector without metadata (should not happen); skip rather than fail
                continue
            chunks.append(ScoredChunk(
                chunk_id=r["chunk_id"], doc_id=r["doc_id"], filename=r["filename"], title=r["title"] or r["filename"],
                page_start=r["page_start"], page_end=r["page_end"], text=r["text"], token_count=r["token_count"],
                bboxes=json.loads(r["bboxes_json"]), lang=r["lang"], dense_rank=h.dense_rank,
                dense_score=h.dense_score, bm25_rank=h.bm25_rank, bm25_score=h.bm25_score,
                rrf_score=round(h.rrf_score, 6)))
        timings["fusion_ms"] = (time.perf_counter() - t) * 1000
        timings["retrieval_ms"] = (time.perf_counter() - t_all) * 1000
        return chunks, timings
