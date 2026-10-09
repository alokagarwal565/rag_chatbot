"""OCR backends. RapidOCR (ONNX, pip-only) by default; Tesseract only if it is found on PATH.

`ocr_task` is the process-pool entry point: it renders a page (or a clip of it) with PyMuPDF and
returns recognised lines with boxes mapped back to PDF points, plus per-line confidence.
"""
import os
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

import numpy as np

from ingestion.config import OCR_BACKEND

# (text, [x0, y0, x1, y1] in PDF points, confidence 0..1)
OcrLine = Tuple[str, List[float], float]

_ENGINE = None
_ENGINE_NAME = None
_DOC_CACHE = {}


def tesseract_path() -> Optional[str]:
    return os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")


def backend_name() -> str:
    want = OCR_BACKEND.lower()
    if want == "tesseract":
        if tesseract_path():
            return "tesseract"
        raise RuntimeError("OCR_BACKEND=tesseract but tesseract was not found on PATH")
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return "rapidocr"
    except ImportError:
        if tesseract_path():
            return "tesseract"
        raise RuntimeError("No OCR backend: install rapidocr-onnxruntime (pip) or Tesseract")


def _rapid():
    global _ENGINE, _ENGINE_NAME
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        # One ONNX thread per worker process: the pool supplies the parallelism.
        threads = int(os.environ.get("OCR_ONNX_THREADS", "1"))
        _ENGINE = RapidOCR(intra_op_num_threads=threads, inter_op_num_threads=1)
        _ENGINE_NAME = "rapidocr"
    return _ENGINE


def _ocr_rapid(img: np.ndarray) -> List[Tuple[str, List[float], float]]:
    result, _ = _rapid()(img)
    out = []
    for box, text, score in result or []:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append((text.strip(), [min(xs), min(ys), max(xs), max(ys)], float(score)))
    return out


def _ocr_tesseract(img: np.ndarray) -> List[Tuple[str, List[float], float]]:
    from PIL import Image
    exe = tesseract_path()
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "page.png")
        Image.fromarray(img).save(p)
        tsv = subprocess.run([exe, p, "stdout", "--psm", "3", "tsv"], capture_output=True, text=True,
                             encoding="utf-8", errors="ignore", check=True).stdout
    lines = {}
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or not cols[11].strip() or cols[10] in ("-1", ""):
            continue
        key = (cols[2], cols[3], cols[4])  # block, paragraph, line
        x, y, w, h, conf = int(cols[6]), int(cols[7]), int(cols[8]), int(cols[9]), float(cols[10])
        ln = lines.setdefault(key, {"words": [], "box": [x, y, x + w, y + h], "conf": []})
        ln["words"].append(cols[11])
        b = ln["box"]
        ln["box"] = [min(b[0], x), min(b[1], y), max(b[2], x + w), max(b[3], y + h)]
        ln["conf"].append(conf / 100.0)
    return [(" ".join(v["words"]), v["box"], sum(v["conf"]) / len(v["conf"])) for v in lines.values()]


def _open(pdf_path: str):
    doc = _DOC_CACHE.get(pdf_path)
    if doc is None:
        import pymupdf as fitz
        for d in _DOC_CACHE.values():
            d.close()
        _DOC_CACHE.clear()
        doc = fitz.open(pdf_path)
        _DOC_CACHE[pdf_path] = doc
    return doc


def render(pdf_path: str, page_no: int, dpi: int, clip: Optional[List[float]] = None) -> np.ndarray:
    import pymupdf as fitz
    page = _open(pdf_path)[page_no - 1]
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY,
                          clip=fitz.Rect(*clip) if clip else None, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def ocr_image(img: np.ndarray, backend: str) -> List[Tuple[str, List[float], float]]:
    return _ocr_tesseract(img) if backend == "tesseract" else _ocr_rapid(img)


def ocr_task(args) -> dict:
    """Process-pool worker. args = (pdf_path, page_no, dpi, clip_or_None, kind, backend)."""
    pdf_path, page_no, dpi, clip, kind, backend = args
    try:
        img = render(pdf_path, page_no, dpi, clip)
        raw = ocr_image(img, backend)
        scale = 72.0 / dpi
        ox, oy = (clip[0], clip[1]) if clip else (0.0, 0.0)
        lines = [(t, [ox + b[0] * scale, oy + b[1] * scale, ox + b[2] * scale, oy + b[3] * scale], c)
                 for t, b, c in raw if t]
        return {"page_no": page_no, "kind": kind, "clip": clip, "lines": lines, "backend": backend, "error": None}
    except Exception as e:  # noqa: BLE001 - reported per page, the run continues
        return {"page_no": page_no, "kind": kind, "clip": clip, "lines": [], "backend": backend, "error": repr(e)}
