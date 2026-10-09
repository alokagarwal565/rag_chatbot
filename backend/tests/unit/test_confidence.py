from app.services.confidence import ConfidenceClassifier


def test_levels():
    assert ConfidenceClassifier.classify(0.95, 3, 0, 0, False) == "HIGH"
    assert ConfidenceClassifier.classify(0.2, 1, 2, 0, False) == "LOW"
    assert ConfidenceClassifier.classify(0.9, 0, 0, 0, False) == "ABSTAIN"
    assert ConfidenceClassifier.classify(0.9, 2, 0, 0, True) == "ABSTAIN"
