"""Per-page extraction with PyMuPDF.

A page is "native" when its text layer has at least NATIVE_MIN_CHARS non-whitespace characters and the
document is not flagged `force_ocr`; otherwise the whole page is rasterised and OCR'd. On native pages,
embedded images covering >= OCR_IMAGE_MIN_AREA_FRAC of the page are OCR'd too (capped per document),
so text inside figures/diagrams becomes searchable.

Blocks keep line-level boxes (PDF points) so the cleaner can find header/footer bands and the chunker
can attach a bounding box per page to every chunk.
"""
from dataclasses import dataclass, field
from typing import List, Optional

import pymupdf as fitz

from ingestion.config import NATIVE_MIN_CHARS, OCR_IMAGE_MIN_AREA_FRAC


@dataclass
class Line:
    text: str
    bbox: List[float]
    conf: Optional[float] = None


@dataclass
class Block:
    lines: List[Line]
    source: str  # "native" | "ocr" | "image_ocr"

    @property
    def bbox(self) -> List[float]:
        xs0, ys0, xs1, ys1 = zip(*(ln.bbox for ln in self.lines))
        return [min(xs0), min(ys0), max(xs1), max(ys1)]

    def to_json(self) -> dict:
        return {"s": self.source, "l": [[ln.text, *[round(v, 1) for v in ln.bbox],
                                         None if ln.conf is None else round(ln.conf, 3)] for ln in self.lines]}

    @staticmethod
    def from_json(d: dict) -> "Block":
        return Block([Line(x[0], list(x[1:5]), x[5] if len(x) > 5 else None) for x in d["l"]], d["s"])


@dataclass
class PageData:
    page_no: int  # 1-based
    width: float
    height: float
    method: str  # native | ocr | native+img_ocr
    blocks: List[Block] = field(default_factory=list)
    ocr_conf: Optional[float] = None
    error: Optional[str] = None

    @property
    def char_count(self) -> int:
        return sum(len(ln.text) for b in self.blocks for ln in b.lines)


def native_blocks(page: fitz.Page) -> List[Block]:
    blocks = []
    for b in page.get_text("dict", sort=True)["blocks"]:
        if b.get("type") != 0:
            continue
        lines = []
        for ln in b["lines"]:
            text = "".join(s["text"] for s in ln["spans"]).strip()
            if text:
                lines.append(Line(text, list(ln["bbox"])))
        if lines:
            blocks.append(Block(lines, "native"))
    return blocks


def is_native(blocks: List[Block], force_ocr: bool) -> bool:
    if force_ocr:
        return False
    chars = sum(len("".join(ln.text.split())) for b in blocks for ln in b.lines)
    return chars >= NATIVE_MIN_CHARS


def large_image_rects(page: fitz.Page) -> List[List[float]]:
    area = page.rect.width * page.rect.height
    out = []
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"]) & page.rect
        if r.is_empty:
            continue
        if r.width * r.height >= OCR_IMAGE_MIN_AREA_FRAC * area:
            out.append([round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)])
    # de-duplicate (the same image can be listed twice)
    uniq = []
    for r in out:
        if r not in uniq:
            uniq.append(r)
    return uniq


def ocr_lines_to_blocks(lines, source: str) -> List[Block]:
    """Groups OCR lines (already roughly top-to-bottom) into paragraph blocks by vertical gaps."""
    if not lines:
        return []
    items = sorted(lines, key=lambda t: (round(t[1][1] / 4), t[1][0]))
    blocks: List[Block] = []
    cur: List[Line] = []
    for text, box, conf in items:
        if cur:
            prev = cur[-1].bbox
            h = max(prev[3] - prev[1], 1.0)
            gap = box[1] - prev[3]
            if gap > 0.9 * h or abs(box[0] - cur[0].bbox[0]) > 6 * h:
                blocks.append(Block(cur, source))
                cur = []
        cur.append(Line(text, list(box), conf))
    if cur:
        blocks.append(Block(cur, source))
    return blocks


def mean_conf(blocks: List[Block]) -> Optional[float]:
    confs = [ln.conf for b in blocks for ln in b.lines if ln.conf is not None]
    return round(sum(confs) / len(confs), 4) if confs else None
