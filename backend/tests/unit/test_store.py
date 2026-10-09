import json

from ingestion.store import Store, fts_query


def test_fts_query_sanitises_operators_and_stopwords():
    assert fts_query('What is "photosynthesis" AND NEAR(x)?') == '"photosynthesis" OR "near"'
    assert fts_query("What is the role of ATP synthase?") == '"role" OR "atp" OR "synthase"'
    assert fts_query("the of is") is None


def test_store_roundtrip_and_bm25(tmp_path):
    s = Store(tmp_path / "t.db")
    s.upsert_document(doc_id="d1", filename="a.pdf", title="A", sha256="x", page_count=2, status="done")
    rows = [
        {"chunk_id": "c1", "doc_id": "d1", "chunk_index": 0, "page_start": 1, "page_end": 1, "token_count": 5,
         "bboxes_json": json.dumps({"1": [0, 0, 1, 1]}), "lang": "en", "has_ocr": 0,
         "text": "Photosynthesis converts light energy into chemical energy in chloroplasts."},
        {"chunk_id": "c2", "doc_id": "d1", "chunk_index": 1, "page_start": 2, "page_end": 2, "token_count": 5,
         "bboxes_json": json.dumps({"2": [0, 0, 1, 1]}), "lang": "en", "has_ocr": 0,
         "text": "Supply and demand determine the market price of goods."},
    ]
    s.replace_chunks("d1", rows)
    hits = s.bm25_search("how do chloroplasts make chemical energy", 5)
    assert hits[0][0] == "c1" and hits[0][1] > 0
    assert s.get_chunks(["c2"])["c2"]["filename"] == "a.pdf"
    # replacing chunks keeps the FTS index in sync (no stale hits)
    s.replace_chunks("d1", rows[1:])
    assert all(cid != "c1" for cid, _ in s.bm25_search("chloroplasts", 5))
    s.delete_document("d1")
    assert s.get_document("d1") is None and s.bm25_search("market price", 5) == []
