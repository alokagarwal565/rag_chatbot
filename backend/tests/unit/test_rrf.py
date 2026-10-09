from app.services.retriever import rrf_fuse


def test_rrf_rewards_agreement_between_lists():
    dense = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
    lexical = [("c", 12.0), ("a", 10.0), ("d", 5.0)]
    fused = rrf_fuse(dense, lexical, k=60)
    ids = [h.chunk_id for h in fused]
    assert ids[0] == "a"            # rank 1 + rank 2
    assert ids[1] == "c"            # rank 3 + rank 1
    assert set(ids) == {"a", "b", "c", "d"}
    a = fused[0]
    assert abs(a.rrf_score - (1 / 61 + 1 / 62)) < 1e-12
    assert (a.dense_rank, a.bm25_rank) == (1, 2)


def test_rrf_single_list_and_deterministic_ties():
    fused = rrf_fuse([("x", 0.5)], [("y", 3.0)], k=60)
    assert [h.chunk_id for h in fused] == ["x", "y"]  # equal scores, equal best rank -> id order
    assert fused[1].dense_rank is None and fused[1].bm25_rank == 1


def test_rrf_empty():
    assert rrf_fuse([], []) == []
