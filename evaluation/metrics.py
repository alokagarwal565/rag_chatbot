import math
from typing import Dict, List, Optional


def first_hit_rank(chunks: List[dict], gold_filename: str, gold_pages: List[int], k: int = 10) -> Optional[int]:
    """1-based rank of the first retrieved chunk from the gold file whose page range covers a gold page."""
    gold = set(gold_pages)
    for i, c in enumerate(chunks[:k], start=1):
        if c["filename"] == gold_filename and gold & set(range(c["page_start"], c["page_end"] + 1)):
            return i
    return None


def recall_at_k(ranks: List[Optional[int]], k: int) -> float:
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks) if ranks else 0.0


def mrr_at_k(ranks: List[Optional[int]], k: int = 10) -> float:
    return sum(1.0 / r for r in ranks if r is not None and r <= k) / len(ranks) if ranks else 0.0


def percentile(values: List[float], p: float) -> Optional[float]:
    """Linear-interpolated percentile (numpy's default method)."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    pos = (len(vals) - 1) * p / 100.0
    lo, hi = math.floor(pos), math.ceil(pos)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def threshold_sweep(scores_answerable: List[float], scores_unanswerable: List[float],
                    thresholds: List[float]) -> List[Dict]:
    """For an evidence gate `abstain if score < t`: share of unanswerable questions correctly abstained and
    share of answerable questions wrongly abstained, per threshold."""
    out = []
    for t in thresholds:
        correct = sum(1 for s in scores_unanswerable if s < t) / max(1, len(scores_unanswerable))
        false = sum(1 for s in scores_answerable if s < t) / max(1, len(scores_answerable))
        out.append({"threshold": t, "correct_abstention": round(correct, 3), "false_abstention": round(false, 3)})
    return out
