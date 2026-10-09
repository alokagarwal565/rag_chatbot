from app.services.answerability import AnswerabilityChecker, sigmoid
from tests.conftest import make_chunk


def test_empty_chunks_abstain():
    a = AnswerabilityChecker(abstain_threshold=0.1).evaluate([])
    assert a.is_sufficient is False and a.evidence_score == 0.0


def test_rerank_probability_gate():
    checker = AnswerabilityChecker(abstain_threshold=0.1)
    strong = make_chunk(rerank_score=3.0, rerank_prob=sigmoid(3.0), rrf_score=0.03)
    weak = make_chunk(rerank_score=-6.0, rerank_prob=sigmoid(-6.0), rrf_score=0.03)
    assert checker.evaluate([strong]).is_sufficient
    assert not checker.evaluate([weak]).is_sufficient
    assert checker.evaluate([strong]).signal == "rerank"


def test_rrf_gate_when_reranker_disabled():
    checker = AnswerabilityChecker(rrf_threshold=0.02)
    assert checker.evaluate([make_chunk(rrf_score=0.032)]).is_sufficient
    assert not checker.evaluate([make_chunk(rrf_score=0.01)]).is_sufficient


def test_sigmoid_is_stable():
    assert sigmoid(-1000) == 0.0 and sigmoid(1000) == 1.0
