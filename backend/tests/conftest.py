import pytest

from app.providers.base import ScoredChunk


def make_chunk(cid="c1", text="Photosynthesis converts light energy into chemical energy.", page=12,
               filename="biology-2e.pdf", **kw) -> ScoredChunk:
    page_end = kw.pop("page_end", page)
    return ScoredChunk(chunk_id=cid, doc_id="d1", filename=filename, title="Biology 2e",
                       page_start=page, page_end=page_end, text=text, token_count=20,
                       bboxes={str(page): [50.0, 60.0, 500.0, 300.0]}, **kw)


@pytest.fixture
def chunk_factory():
    return make_chunk
