from ingestion.chunker import Unit, chunk_id, chunk_units, split_sentences
from ingestion.clean import CleanBlock, CleanPage


def count(texts):
    """Whitespace tokenizer stand-in: deterministic and easy to reason about."""
    return [len(t.split()) for t in texts]


def make_units(n_sentences=200, words=20, pages=10):
    units = []
    for i in range(n_sentences):
        text = " ".join(f"W{i}x{j}" for j in range(words - 1)) + "."
        units.append(Unit(text, page=1 + i * pages // n_sentences, bbox=[10, 10 + i, 200, 20 + i], tokens=words, ocr=False))
    return units


def test_chunks_respect_target_cap_and_overlap():
    units = make_units()
    chunks = chunk_units("doc", units, count, target=480, max_tokens=510, overlap=72)
    assert len(chunks) > 5
    assert all(c.token_count <= 510 for c in chunks)
    assert all(c.token_count >= 400 for c in chunks[:-1])
    # consecutive chunks overlap by whole sentences totalling ~72 tokens (10-30% of the chunk)
    for a, b in zip(chunks, chunks[1:]):
        a_sents, b_sents = split_sentences(a.text), split_sentences(b.text)
        shared = [s for s in b_sents if s in a_sents]
        overlap_tokens = sum(len(s.split()) for s in shared)
        assert 0.10 * a.token_count <= overlap_tokens <= 0.30 * a.token_count


def test_chunking_is_deterministic_with_stable_ids():
    u = make_units()
    a = chunk_units("doc", u, count)
    b = chunk_units("doc", make_units(), count)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]
    assert a[0].chunk_id == chunk_id("doc", 0, a[0].text)
    assert chunk_units("other", u, count)[0].chunk_id != a[0].chunk_id


def test_chunk_metadata_pages_and_bbox_union():
    chunks = chunk_units("doc", make_units(), count)
    c = chunks[0]
    assert c.page_start == 1 and c.page_end >= c.page_start
    assert set(c.bboxes) == {str(p) for p in range(c.page_start, c.page_end + 1)} & set(c.bboxes)
    box = c.bboxes["1"]
    assert box[0] == 10 and box[2] == 200 and box[1] == 10


def test_oversized_sentence_is_split_under_cap():
    from ingestion.chunker import build_units
    long_text = " ".join(f"tok{i}" for i in range(1500))
    page = CleanPage(1, 600, 800, "native", [CleanBlock(long_text, [0, 0, 100, 100], "native")], "en", None, 0)
    units = build_units([page], count, max_tokens=510)
    assert all(u.tokens <= 510 for u in units)
    assert sum(u.tokens for u in units) == 1500
    chunks = chunk_units("doc", units, count)
    assert all(ch.token_count <= 510 for ch in chunks)


def test_ocr_flag_propagates():
    units = make_units(30)
    units[3].ocr = True
    chunks = chunk_units("doc", units, count)
    assert chunks[0].has_ocr
