import json
import time

from fastapi import APIRouter, Request

from app.api.v1.documents import document_item
from ingestion import config as icfg

router = APIRouter()


@router.get("/ingestion/status", tags=["Ingestion"])
def ingestion_status(request: Request):
    store = request.app.state.store
    docs = store.list_documents()
    last = store.last_run()
    recent = any(d["updated_at"] and time.time() - d["updated_at"] < 120 for d in docs)
    totals = store.totals()
    try:
        totals["vectors"] = request.app.state.vectors.count()
    except Exception:  # noqa: BLE001
        totals["vectors"] = 0
    return {
        "documents": [document_item(d).model_dump() for d in docs],
        "totals": totals,
        "running": bool(last and last["status"] == "running" and recent),
        "last_run": None if last is None else {
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last["started_at"])),
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last["finished_at"])) if last["finished_at"] else None,
            "status": last["status"], "stage_timings": json.loads(last["stage_timings"] or "{}")},
        "config": {
            "embedding_model": icfg.EMBEDDING_MODEL, "chunk_target_tokens": icfg.CHUNK_TARGET_TOKENS,
            "chunk_max_tokens": icfg.CHUNK_MAX_TOKENS, "chunk_overlap_tokens": icfg.CHUNK_OVERLAP_TOKENS,
            "ocr_dpi": icfg.OCR_DPI, "ocr_images_per_doc": icfg.OCR_IMAGES_PER_DOC,
            "native_min_chars": icfg.NATIVE_MIN_CHARS,
        },
    }
