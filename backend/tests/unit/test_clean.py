from ingestion.clean import clean_document, normalize_text
from ingestion.extract import Block, Line, PageData

H = 800.0


def page(pno, body, header=None, footer=None, number=True):
    blocks = []
    if header:
        blocks.append(Block([Line(header, [50, 20, 400, 32])], "native"))
    blocks.append(Block([Line(t, [50, 100 + 14 * i, 500, 112 + 14 * i]) for i, t in enumerate(body)], "native"))
    if footer:
        blocks.append(Block([Line(footer, [50, 760, 400, 772])], "native"))
    if number:
        blocks.append(Block([Line(str(pno), [290, 780, 310, 792])], "native"))
    return PageData(pno, 600.0, H, "native", blocks)


def test_repeating_header_footer_and_page_numbers_removed():
    pages = [page(i, [f"Unique body sentence number {i} about cells and energy."],
                  header=f"Chapter 3 | Biological Macromolecules" if i % 2 == 0 else f"3.{i % 5} Synthesis",
                  footer="Access for free at example.org") for i in range(1, 41)]
    cleaned = clean_document(pages)
    for cp in cleaned:
        assert "Access for free" not in cp.text
        assert "Biological Macromolecules" not in cp.text
        assert "Unique body sentence" in cp.text
        assert not any(b.text.strip().isdigit() for b in cp.blocks)


def test_body_lines_outside_bands_are_kept_even_if_repeated():
    pages = [page(i, ["Key concept: energy is conserved.", f"Detail {i}."], number=False) for i in range(1, 21)]
    cleaned = clean_document(pages)
    assert all("Key concept" in cp.text for cp in cleaned)


def test_rare_band_line_kept():
    pages = [page(i, [f"Body {i} text here with enough words."], number=False) for i in range(1, 30)]
    pages[5].blocks.insert(0, Block([Line("A one-off heading at the top", [50, 20, 400, 32])], "native"))
    cleaned = clean_document(pages)
    assert "one-off heading" in cleaned[5].text


def test_normalize_text_hyphenation_unicode_whitespace():
    assert normalize_text("photo-\nsynthesis  is  ﬁne") == "photosynthesis is fine"
    assert normalize_text("self-\nAssessment") == "self- Assessment"  # capitalised: not a word break


def test_language_detection_deterministic():
    body = ["The mitochondria is the powerhouse of the cell and produces most of the chemical energy."] * 3
    a = clean_document([page(1, body)])[0].lang
    b = clean_document([page(1, body)])[0].lang
    assert a == b == "en"
