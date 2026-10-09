from app.services.citation_validator import CitationValidator, count_uncited_sentences
from tests.conftest import make_chunk


def _ctx():
    return [make_chunk("a", page=10), make_chunk("b", page=20, filename="chemistry-2e.pdf")]


def test_valid_markers_map_to_file_and_page():
    r = CitationValidator.validate("Plants make sugar [1]. Atoms bond [2].", _ctx())
    assert not r.abstained
    assert [(c.n, c.filename, c.page_label) for c in r.citations] == [
        (1, "biology-2e.pdf", "p.10"), (2, "chemistry-2e.pdf", "p.20")]


def test_invalid_markers_are_stripped():
    r = CitationValidator.validate("Plants make sugar [1][7]. Made up fact [9].", _ctx())
    assert "[7]" not in r.answer and "[9]" not in r.answer and "[1]" in r.answer
    assert r.invalid_markers == 2 and r.cited_chunk_ids == ["a"]


def test_grouped_and_range_markers_are_normalised():
    r = CitationValidator.validate("Both are true [1, 2]. Also [1-2].", _ctx())
    assert "[1][2]" in r.answer and len(r.citations) == 2


def test_sentinel_and_no_valid_citation_abstain():
    assert CitationValidator.validate("INSUFFICIENT_CONTEXT", _ctx()).abstained
    assert CitationValidator.validate("Something with no source at all [5].", _ctx()).abstained


def test_uncited_sentence_count():
    assert count_uncited_sentences("This sentence has quite a few words but no marker. Short one [1].") == 1
