from fastapi import APIRouter, Request

from app.config import settings

router = APIRouter()


@router.get("/health", tags=["Health"])
@router.head("/health", tags=["Health"])
def health_check(request: Request):
    st = request.app.state
    store = getattr(st, "store", None)
    totals = store.totals() if store else {"documents": 0, "chunks": 0}
    try:
        vectors = st.vectors.count()
    except Exception:  # noqa: BLE001
        vectors = 0
    llm = getattr(st, "llm", None)
    return {
        "status": "ok",
        "service": "granth",
        "documents": totals["documents"],
        "chunks": totals["chunks"],
        "vectors": vectors,
        "models_warm": bool(getattr(st, "models_warm", False)),
        "reranker_enabled": settings.reranker_enabled and getattr(st, "reranker", None) is not None,
        "llm_configured": bool(llm and llm.available),
    }
