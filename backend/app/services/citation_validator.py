"""Validates `[n]` citation markers in a generated answer against the context sources.

- Markers like `[1, 3]` or `[2-4]` are normalised to `[1][3]` / `[2][3][4]`.
- Markers that point outside the provided sources are stripped (and counted).
- The answer abstains if the model returned the abstain sentinel or no valid citation survives.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List

from app.prompts.answer_prompt import ABSTAIN_SENTINEL
from app.providers.base import ScoredChunk

_MARKER_RE = re.compile(r"\[(\s*\d+(?:\s*(?:,|-|–)\s*\d+)*\s*)\]")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Citation:
    n: int
    chunk_id: str
    doc_id: str
    filename: str
    title: str
    page_start: int
    page_end: int
    page_label: str
    excerpt: str
    bboxes: Dict[str, List[float]]


@dataclass
class CitationValidationResult:
    answer: str
    citations: List[Citation] = field(default_factory=list)
    invalid_markers: int = 0
    valid_markers: int = 0
    uncited_sentences: int = 0
    abstained: bool = False

    @property
    def cited_chunk_ids(self) -> List[str]:
        return [c.chunk_id for c in self.citations]


def _expand(spec: str) -> List[int]:
    nums: List[int] = []
    for part in re.split(r"\s*,\s*", spec.strip()):
        m = re.match(r"(\d+)\s*[-–]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b and b - a <= 10:
                nums.extend(range(a, b + 1))
                continue
        if part.isdigit():
            nums.append(int(part))
    return nums


def count_uncited_sentences(answer: str) -> int:
    """Factual-looking sentences (>= 8 words) without any citation marker."""
    count = 0
    for line in answer.splitlines():
        for sent in _SENTENCE_RE.split(line.strip()):
            if len(sent.split()) >= 8 and not _MARKER_RE.search(sent):
                count += 1
    return count


class CitationValidator:
    @staticmethod
    def validate(answer_text: str, context_chunks: List[ScoredChunk]) -> CitationValidationResult:
        text = (answer_text or "").strip()
        if not text or text.strip(" .").upper() == ABSTAIN_SENTINEL or text.startswith(ABSTAIN_SENTINEL):
            return CitationValidationResult(answer="", abstained=True)

        n_sources = len(context_chunks)
        cited: Dict[int, Citation] = {}
        invalid = 0
        valid = 0

        def _replace(m: re.Match) -> str:
            nonlocal invalid, valid
            out = []
            for n in _expand(m.group(1)):
                if 1 <= n <= n_sources:
                    valid += 1
                    if n not in cited:
                        c = context_chunks[n - 1]
                        excerpt = c.text[:400] + ("…" if len(c.text) > 400 else "")
                        cited[n] = Citation(
                            n=n, chunk_id=c.chunk_id, doc_id=c.doc_id, filename=c.filename,
                            title=c.title, page_start=c.page_start, page_end=c.page_end,
                            page_label=c.page_label(), excerpt=excerpt, bboxes=c.bboxes)
                    if f"[{n}]" not in out:
                        out.append(f"[{n}]")
                else:
                    invalid += 1
            return "".join(out)

        cleaned = _MARKER_RE.sub(_replace, text)
        cleaned = cleaned.replace(ABSTAIN_SENTINEL, "").strip()
        cleaned = re.sub(r"[ \t]+([.,;:])", r"\1", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)

        result = CitationValidationResult(
            answer=cleaned,
            citations=[cited[k] for k in sorted(cited)],
            invalid_markers=invalid,
            valid_markers=valid,
            uncited_sentences=count_uncited_sentences(cleaned),
        )
        if not result.citations:
            result.abstained = True
        return result
