import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from app.api.v1.documents import router as documents_router  # noqa: E402
from app.api.v1.evaluation import router as evaluation_router  # noqa: E402
from app.api.v1.health import router as health_router  # noqa: E402
from app.api.v1.ingestion import router as ingestion_router  # noqa: E402
from app.api.v1.query import router as query_router  # noqa: E402
from app.config import settings  # noqa: E402
from app.logging_config import configure_logging, ctx_request_id, get_logger  # noqa: E402
from app.providers.gemini_provider import GeminiProvider  # noqa: E402
from app.services.query_service import QueryService  # noqa: E402
from app.services.retriever import HybridRetriever  # noqa: E402
from ingestion.embedder import get_embedder  # noqa: E402
from ingestion.store import Store  # noqa: E402
from ingestion.vector_store import VectorStore  # noqa: E402

configure_logging(settings.log_level)
logger = get_logger(__name__)


def _load_models():
    """Load and warm every local model so the first user query pays no load cost."""
    t = time.perf_counter()
    embedder = get_embedder()
    embedder.embed_query("warm up the embedding model")
    reranker = None
    if settings.reranker_enabled:
        from app.providers.fastembed_provider import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        reranker.score("warm up", ["the reranker model", "with two passages"])
    logger.info("models_warm", seconds=round(time.perf_counter() - t, 1), reranker=bool(reranker))
    return embedder, reranker


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.models_warm = False
    app.state.store = Store()
    app.state.vectors = VectorStore()
    app.state.llm = GeminiProvider()
    embedder, reranker = await run_in_threadpool(_load_models)
    app.state.embedder = embedder
    app.state.reranker = reranker
    retriever = HybridRetriever(app.state.store, app.state.vectors, embedder)
    try:
        retriever.retrieve("warm up the indexes")  # opens the HNSW index and FTS tables
    except Exception as e:  # noqa: BLE001 - empty index on a fresh install
        logger.warning("index_warmup_skipped", error=str(e)[:200])
    app.state.query_service = QueryService(retriever, reranker, app.state.llm)
    app.state.models_warm = True
    if settings.llm_warmup and app.state.llm.available:
        # Opens the TLS connection to the LLM API in the background (1-token request).
        async def _warm_llm():
            try:
                await app.state.llm.generate("Reply with OK.", None, max_tokens=1, timeout=10)
                logger.info("llm_warm")
            except Exception as e:  # noqa: BLE001
                logger.warning("llm_warmup_failed", error=str(e)[:200])
        asyncio.create_task(_warm_llm())
    logger.info("service_ready", documents=app.state.store.totals()["documents"], vectors=app.state.vectors.count(),
                llm_keys=len(app.state.llm.api_keys))
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Granth API",
        description="Open-source PDF knowledge assistant: hybrid retrieval (HNSW + BM25 + RRF + cross-encoder) "
                    "and grounded, page-cited answers.",
        version="1.0.0",
        lifespan=lifespan,
    )
    origins = {settings.frontend_url, "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"}
    app.add_middleware(CORSMiddleware, allow_origins=sorted(origins), allow_credentials=False,
                       allow_methods=["GET", "POST", "OPTIONS", "HEAD"], allow_headers=["Content-Type", "X-Request-ID"])

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = ctx_request_id.set(req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            ctx_request_id.reset(token)

    app.include_router(health_router)
    for r in (health_router, query_router, documents_router, ingestion_router, evaluation_router):
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
