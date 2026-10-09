"""Text cleaning: repeating header/footer removal, page numbers, unicode, hyphenation, whitespace,
language detection.

Header/footer detection is statistical, not regex-per-publisher: a line in the top or bottom
HF_BAND_FRAC of the page is dropped when its normalised form (lower-case, digits -> '#') recurs on
at least max(HF_MIN_PAGES, HF_MIN_PAGE_FRAC * window) pages inside a sliding HF_WINDOW-page window.
That catches running heads ("Chapter 3 | Macromolecules"), alternating odd/even heads, and footers
like "Access for free at ..." while leaving body text alone.
"""
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from langdetect import DetectorFactory, LangDetectException, detect

from ingestion.config import HF_BAND_FRAC, HF_MIN_PAGE_FRAC, HF_MIN_PAGES, HF_WINDOW
from ingestion.extract import PageData

DetectorFactory.seed = 0  # langdetect is randomised; seeding makes it deterministic

_PAGE_NUM_RE = re.compile(r"^\s*(?:page\s*)?(?:\d{1,4}|[ivxlcdm]{1,7})(?:\s*(?:of|/)\s*\d{1,4})?\s*$", re.IGNORECASE)
_HYPHEN_RE = re.compile(r"(\w)[-­]\n([a-z])")
_WS_RE = re.compile(r"[ \t  -​]+")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class CleanBlock:
    text: str
    bbox: List[float]
    source: str


@dataclass
class CleanPage:
    page_no: int
    width: float
    height: float
    method: str
    blocks: List[CleanBlock]
    lang: Optional[str]
    ocr_conf: Optional[float]
    removed_lines: int

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)


def _key(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"\d+", "#", t)
    return " ".join(t.split())


def _in_band(bbox: List[float], height: float) -> bool:
    band = HF_BAND_FRAC * height
    yc = (bbox[1] + bbox[3]) / 2
    return yc <= band or yc >= height - band


def find_repeating_lines(pages: List[PageData]) -> Set[Tuple[int, str]]:
    """Returns (page_no, key) pairs for band lines that recur across nearby pages."""
    occurrences: Dict[str, List[int]] = defaultdict(list)
    for p in pages:
        seen = set()
        for b in p.blocks:
            for ln in b.lines:
                if _in_band(ln.bbox, p.height):
                    k = _key(ln.text)
                    if k and k not in seen:
                        seen.add(k)
                        occurrences[k].append(p.page_no)
    n_pages = len(pages)
    half = HF_WINDOW // 2
    flagged: Set[Tuple[int, str]] = set()
    for k, pnos in occurrences.items():
        if len(pnos) < HF_MIN_PAGES:
            continue
        for i, pno in enumerate(pnos):
            lo, hi = pno - half, pno + half
            window = min(hi, n_pages) - max(lo, 1) + 1
            count = sum(1 for q in pnos if lo <= q <= hi)
            if count >= max(HF_MIN_PAGES, HF_MIN_PAGE_FRAC * window):
                flagged.add((pno, k))
    return flagged


def normalize_text(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = _CTRL_RE.sub("", t)
    t = t.replace("ﬁ", "fi").replace("ﬂ", "fl")
    t = _HYPHEN_RE.sub(r"\1\2", t)
    t = t.replace("\n", " ")
    return _WS_RE.sub(" ", t).strip()


def detect_lang(text: str) -> Optional[str]:
    sample = text[:1500]
    if len(sample.strip()) < 50:
        return None
    try:
        return detect(sample)
    except LangDetectException:
        return None


def clean_document(pages: List[PageData]) -> List[CleanPage]:
    flagged = find_repeating_lines(pages)
    out: List[CleanPage] = []
    for p in pages:
        removed = 0
        blocks: List[CleanBlock] = []
        for b in p.blocks:
            kept = []
            for ln in b.lines:
                band = _in_band(ln.bbox, p.height)
                if band and ((p.page_no, _key(ln.text)) in flagged or _PAGE_NUM_RE.match(ln.text)):
                    removed += 1
                    continue
                kept.append(ln)
            if not kept:
                continue
            text = normalize_text("\n".join(ln.text for ln in kept))
            if not text:
                continue
            xs0, ys0, xs1, ys1 = zip(*(ln.bbox for ln in kept))
            blocks.append(CleanBlock(text, [min(xs0), min(ys0), max(xs1), max(ys1)], b.source))
        page_text = " ".join(b.text for b in blocks)
        out.append(CleanPage(p.page_no, p.width, p.height, p.method, blocks, detect_lang(page_text),
                             p.ocr_conf, removed))
    return out


def document_language(pages: List[CleanPage]) -> Optional[str]:
    c = Counter(p.lang for p in pages if p.lang)
    return c.most_common(1)[0][0] if c else None
