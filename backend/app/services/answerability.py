import math
from dataclasses import dataclass
from typing import List

from app.config import settings
from app.providers.base import ScoredChunk


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass
class EvidenceAssessment:
    evidence_score: float
    is_sufficient: bool
    reason: str
    signal: str  # "rerank" or "rrf"


class AnswerabilityChecker:
    """Evidence gate run before the LLM. Uses the reranker's calibrated probability of the best
    chunk when available, otherwise the best RRF score (dense+lexical agreement)."""

    def __init__(self, abstain_threshold: float = None, rrf_threshold: float = None):
        self.abstain_threshold = settings.abstain_threshold if abstain_threshold is None else abstain_threshold
        self.rrf_threshold = settings.rrf_abstain_threshold if rrf_threshold is None else rrf_threshold

    def evaluate(self, chunks: List[ScoredChunk]) -> EvidenceAssessment:
        if not chunks:
            return EvidenceAssessment(0.0, False, "No passages were retrieved for this question.", "none")

        top = chunks[0]
        if top.rerank_prob is not None:
            score, threshold, signal = top.rerank_prob, self.abstain_threshold, "rerank"
        else:
            score, threshold, signal = top.rrf_score, self.rrf_threshold, "rrf"

        ok = score >= threshold
        reason = ("Sufficient evidence found." if ok else
                  "The indexed documents don't appear to contain an answer to this question.")
        return EvidenceAssessment(round(score, 4), ok, reason, signal)
