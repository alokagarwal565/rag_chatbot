from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol


@dataclass
class ScoredChunk:
    chunk_id: str
    doc_id: str
    filename: str
    title: str
    page_start: int
    page_end: int
    text: str
    token_count: int
    # page number (as str, JSON-friendly) -> [x0, y0, x1, y1] in PDF points
    bboxes: Dict[str, List[float]] = field(default_factory=dict)
    lang: Optional[str] = None
    dense_rank: Optional[int] = None
    dense_score: Optional[float] = None  # cosine similarity
    bm25_rank: Optional[int] = None
    bm25_score: Optional[float] = None  # positive: higher is better
    rrf_score: float = 0.0
    rerank_score: Optional[float] = None  # raw cross-encoder logit
    rerank_prob: Optional[float] = None  # sigmoid(logit)

    def page_label(self) -> str:
        if self.page_start == self.page_end:
            return f"p.{self.page_start}"
        return f"pp.{self.page_start}-{self.page_end}"


class EmbeddingProvider(Protocol):
    def embed_query(self, text: str) -> List[float]:
        ...


class Reranker(Protocol):
    def rerank(self, query: str, candidates: List[ScoredChunk], top_k: int) -> List[ScoredChunk]:
        ...
