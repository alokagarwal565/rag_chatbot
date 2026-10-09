import json
import threading
from collections import OrderedDict
from typing import List

import pymupdf as fitz
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from app.models.schemas import DocumentItem
from ingestion.config import PDF_DIR

router = APIRouter()

_CACHE_MAX = 96
_png_cache: "OrderedDict[tuple, bytes]" = OrderedDict()
_cache_lock = threading.Lock()


def document_item(r) -> DocumentItem:
    return DocumentItem(
        doc_id=r["doc_id"], filename=r["filename"], title=r["title"] or r["filename"], page_count=r["page_count"] or 0,
        native_pages=r["native_pages"] or 0, ocr_pages=r["ocr_pages"] or 0, chunk_count=r["chunk_count"] or 0,
        language=r["language"], status=r["status"], stage=r["stage"],
        stage_timings=json.loads(r["stage_timings"] or "{}"), source_url=r["source_url"], license=r["license"],
        ingested_at=str(r["ingested_at"]) if r["ingested_at"] else None)


@router.get("/documents", response_model=List[DocumentItem], tags=["Documents"])
def list_documents(request: Request):
    return [document_item(r) for r in request.app.state.store.list_documents()]


@router.get("/documents/{doc_id}/page/{page_no}/image", tags=["Documents"],
            responses={200: {"content": {"image/png": {}}}})
def page_image(doc_id: str, page_no: int, request: Request, dpi: int = Query(110, ge=36, le=200)):
    """Renders one PDF page as PNG (used for citation previews; bbox overlays are drawn client-side
    by scaling PDF points by dpi/72)."""
    key = (doc_id, page_no, dpi)
    with _cache_lock:
        if key in _png_cache:
            _png_cache.move_to_end(key)
            return Response(_png_cache[key], media_type="image/png", headers={"Cache-Control": "max-age=86400"})
    doc = request.app.state.store.get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "unknown document")
    path = PDF_DIR / doc["filename"]
    if not path.exists():
        raise HTTPException(404, "PDF file missing from data/pdfs")
    with fitz.open(path) as pdf:
        if not 1 <= page_no <= pdf.page_count:
            raise HTTPException(404, "page out of range")
        png = pdf[page_no - 1].get_pixmap(dpi=dpi, alpha=False).tobytes("png")
    with _cache_lock:
        _png_cache[key] = png
        while len(_png_cache) > _CACHE_MAX:
            _png_cache.popitem(last=False)
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=86400"})
