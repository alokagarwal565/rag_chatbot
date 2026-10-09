import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.logging_config import ctx_request_id, get_logger
from app.models.schemas import QueryRequest
from app.services.query_router import ROUTE_RAG, QueryRouter

router = APIRouter()
logger = get_logger(__name__)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/query", tags=["Query"], summary="Ask a question (Server-Sent Events stream)")
async def query(req: QueryRequest, request: Request):
    """Events: `status`, `rewrite`, `retrieval` (top chunks with scores), `token` (answer deltas),
    `final` (answer, citations, chunks with dense/BM25/RRF/rerank scores, per-stage timings),
    `fast_path` / `decline` (router replies), `error`, `done`."""
    service = getattr(request.app.state, "query_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail={"request_id": ctx_request_id.get(),
                                                     "error_code": "SERVICE_INITIALIZING",
                                                     "message": "Models are still loading; retry in a few seconds."})

    async def stream():
        try:
            decision = QueryRouter.classify(req.question, req.conversation_history)
            if decision.route != ROUTE_RAG:
                yield sse(decision.route, {"message": decision.fast_response, "category": decision.category})
                yield sse("done", {})
                return
            async for ev in service.run_streaming(req.question, req.conversation_history, req.doc_ids, req.rerank):
                yield sse(ev.type, ev.data)
        except asyncio.CancelledError:
            pass  # client disconnected
        except Exception as e:  # noqa: BLE001
            logger.error("stream_failed", error=repr(e))
            yield sse("error", {"message": "Internal error while answering."})
            yield sse("done", {})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
