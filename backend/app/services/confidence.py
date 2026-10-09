from typing import Literal

ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW", "ABSTAIN"]


class ConfidenceClassifier:
    @staticmethod
    def classify(evidence_score: float, cited_sources: int, uncited_sentences: int,
                 invalid_markers: int, abstained: bool) -> ConfidenceLevel:
        """Combines evidence strength (rerank probability) with citation coverage."""
        if abstained or cited_sources == 0:
            return "ABSTAIN"
        score = 0.6 * min(evidence_score, 1.0) + 0.4 * min(cited_sources / 2.0, 1.0)
        score -= 0.1 * min(uncited_sentences, 3)
        score -= 0.1 * min(invalid_markers, 2)
        if score >= 0.65:
            return "HIGH"
        if score >= 0.4:
            return "MEDIUM"
        return "LOW"
