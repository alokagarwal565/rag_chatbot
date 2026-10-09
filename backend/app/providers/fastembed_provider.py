"""ONNX cross-encoder reranker (fastembed TextCrossEncoder), CPU only.

Benchmark on an i3-8130U (scripts/bench_models.py): ms-marco-MiniLM-L-6-v2 takes ~4.2 s for 20 pairs at
512 tokens but ~0.76 s for 12 pairs truncated to 256 tokens, so the defaults are 12 candidates / 256 tokens.
"""
import os
from typing import List

from app.config import settings
from app.providers.base import ScoredChunk
from app.services.answerability import sigmoid
from ingestion.config import MODEL_CACHE_DIR

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


class CrossEncoderReranker:
    def __init__(self, model_name: str = None, max_length: int = None, threads: int = None):
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        self.model_name = model_name or settings.reranker_model
        self.max_length = max_length or settings.reranker_max_length
        self.model = TextCrossEncoder(self.model_name, cache_dir=str(MODEL_CACHE_DIR),
                                      threads=threads or os.cpu_count() or 4)
        self.model.model.tokenizer.enable_truncation(max_length=self.max_length)

    def score(self, query: str, texts: List[str]) -> List[float]:
        if not texts:
            return []
        return [float(s) for s in self.model.rerank(query, texts, batch_size=len(texts))]

    def rerank(self, query: str, candidates: List[ScoredChunk], top_k: int = None) -> List[ScoredChunk]:
        """Scores every candidate, sorts by relevance (desc) and returns the first top_k (all by default)."""
        scores = self.score(query, [c.text for c in candidates])
        for c, s in zip(candidates, scores):
            c.rerank_score = round(s, 4)
            c.rerank_prob = round(sigmoid(s), 4)
        ranked = sorted(candidates, key=lambda c: c.rerank_score, reverse=True)
        return ranked[:top_k] if top_k else ranked
