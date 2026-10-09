"""Deterministic token-window chunker.

The document is flattened into sentence units (each knows its page and the bbox of the block it came
from). Units are packed greedily up to CHUNK_TARGET_TOKENS; the next chunk restarts from the trailing
units that add up to ~CHUNK_OVERLAP_TOKENS (sentence-aligned overlap). Tokens are counted with the
embedding model's own tokenizer and every chunk is guaranteed <= CHUNK_MAX_TOKENS (the model window is
512 including [CLS]/[SEP]). Sentences longer than the cap are split on token boundaries.

chunk_id = sha1(doc_id | chunk_index | text)[:16] — the same input always yields the same chunks/ids.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List

from ingestion.clean import CleanPage
from ingestion.config import CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS, CHUNK_TARGET_TOKENS

_SENT_RE = re.compile(r"(?<=[.!?:;])\s+(?=[\"'(\[]?[A-Z0-9])")

TokenCounter = Callable[[List[str]], List[int]]


@dataclass
class Unit:
    text: str
    page: int
    bbox: List[float]
    tokens: int
    ocr: bool


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    chunk_index: int
    text: str
    token_count: int
    page_start: int
    page_end: int
    bboxes: Dict[str, List[float]] = field(default_factory=dict)
    has_ocr: bool = False
    lang: str = None

    def to_row(self) -> dict:
        return {"chunk_id": self.chunk_id, "doc_id": self.doc_id, "chunk_index": self.chunk_index,
                "page_start": self.page_start, "page_end": self.page_end, "token_count": self.token_count,
                "bboxes_json": json.dumps(self.bboxes), "lang": self.lang, "has_ocr": int(self.has_ocr),
                "text": self.text}


def chunk_id(doc_id: str, index: int, text: str) -> str:
    return hashlib.sha1(f"{doc_id}|{index}|{text}".encode("utf-8")).hexdigest()[:16]


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENT_RE.split(text) if s.strip()]


def build_units(pages: List[CleanPage], count: TokenCounter, max_tokens: int = CHUNK_MAX_TOKENS,
                tokenizer=None) -> List[Unit]:
    raw = []
    for p in pages:
        for b in p.blocks:
            for s in split_sentences(b.text):
                raw.append((s, p.page_no, b.bbox, b.source != "native"))
    counts = count([r[0] for r in raw]) if raw else []
    units: List[Unit] = []
    for (text, page, bbox, ocr), n in zip(raw, counts):
        if n <= max_tokens:
            units.append(Unit(text, page, bbox, n, ocr))
            continue
        # Over-long "sentence" (tables, run-on OCR): split on word boundaries into <= max_tokens pieces.
        words = text.split()
        piece: List[str] = []
        for w in words:
            piece.append(w)
            if len(piece) % 32 == 0 and count([" ".join(piece)])[0] > max_tokens - 40:
                units.append(Unit(" ".join(piece), page, bbox, count([" ".join(piece)])[0], ocr))
                piece = []
        if piece:
            units.append(Unit(" ".join(piece), page, bbox, count([" ".join(piece)])[0], ocr))
    return units


def _union(boxes: List[List[float]]) -> List[float]:
    return [round(min(b[0] for b in boxes), 1), round(min(b[1] for b in boxes), 1),
            round(max(b[2] for b in boxes), 1), round(max(b[3] for b in boxes), 1)]


_JOIN_HYPHEN_RE = re.compile(r"(\w)- ([a-z])")


def join_units(units: List[Unit]) -> str:
    """Joins sentence units; a word hyphenated across a block/line boundary ("under- side") is rejoined."""
    return _JOIN_HYPHEN_RE.sub(lambda m: m.group(1) + m.group(2), " ".join(u.text for u in units))


def _make_chunk(doc_id: str, index: int, units: List[Unit], count: TokenCounter, lang_by_page: Dict[int, str]) -> Chunk:
    text = join_units(units)
    by_page: Dict[int, List[List[float]]] = {}
    for u in units:
        by_page.setdefault(u.page, []).append(u.bbox)
    pages = sorted(by_page)
    langs = [lang_by_page.get(p) for p in pages if lang_by_page.get(p)]
    return Chunk(chunk_id=chunk_id(doc_id, index, text), doc_id=doc_id, chunk_index=index, text=text,
                 token_count=count([text])[0], page_start=pages[0], page_end=pages[-1],
                 bboxes={str(p): _union(by_page[p]) for p in pages}, has_ocr=any(u.ocr for u in units),
                 lang=max(set(langs), key=langs.count) if langs else None)


def chunk_units(doc_id: str, units: List[Unit], count: TokenCounter, lang_by_page: Dict[int, str] = None,
                target: int = CHUNK_TARGET_TOKENS, max_tokens: int = CHUNK_MAX_TOKENS,
                overlap: int = CHUNK_OVERLAP_TOKENS) -> List[Chunk]:
    lang_by_page = lang_by_page or {}
    chunks: List[Chunk] = []
    i, n = 0, len(units)
    while i < n:
        j, total = i, 0
        while j < n and (total + units[j].tokens <= target or j == i):
            total += units[j].tokens
            j += 1
        group = units[i:j]
        ch = _make_chunk(doc_id, len(chunks), group, count, lang_by_page)
        # Joining sentences can add a token or two; drop trailing units until under the hard cap.
        while ch.token_count > max_tokens and len(group) > 1:
            group = group[:-1]
            j -= 1
            ch = _make_chunk(doc_id, len(chunks), group, count, lang_by_page)
        chunks.append(ch)
        if j >= n:
            break
        # Overlap: step back over trailing units totalling ~overlap tokens, always advancing by >= 1 unit.
        k, back = j, 0
        while k - 1 > i and back + units[k - 1].tokens <= overlap * 1.5 and back < overlap:
            k -= 1
            back += units[k].tokens
        i = k
    return chunks


def chunk_document(doc_id: str, pages: List[CleanPage], count: TokenCounter) -> List[Chunk]:
    units = build_units(pages, count)
    return chunk_units(doc_id, units, count, {p.page_no: p.lang for p in pages})
