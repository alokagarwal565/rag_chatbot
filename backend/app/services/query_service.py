"""Query pipeline (streamed as SSE events):

  rewrite (follow-ups only) -> hybrid retrieve (dense ‖ BM25) -> RRF -> rerank -> evidence gate
  -> Gemini stream over the top-K sources -> citation validation -> final event with scores + timings.
"""
import time
from typing import AsyncGenerator, Dict, List, Optional

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.logging_config import get_logger
from app.models.schemas import ConversationTurn, StreamEvent
from app.prompts.answer_prompt import (ABSTAIN_SENTINEL, REWRITE_SYSTEM_PROMPT, SYSTEM_PROMPT,
                                       build_grounded_prompt, build_rewrite_prompt)
from app.providers.base import ScoredChunk
from app.services.answerability import AnswerabilityChecker
from app.services.citation_validator import CitationValidator
from app.services.confidence import ConfidenceClassifier
from app.services.context_manager import build_effective_query, needs_rewrite, trim_history
from app.services.retriever import HybridRetriever

logger = get_logger(__name__)


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def chunk_payload(c: ScoredChunk, rank: int, context_n: Optional[int], cited: bool) -> dict:
    return {
        "rank": rank, "chunk_id": c.chunk_id, "doc_id": c.doc_id, "filename": c.filename, "title": c.title,
        "page_start": c.page_start, "page_end": c.page_end, "page_label": c.page_label(),
        "snippet": c.text[:220] + ("…" if len(c.text) > 220 else ""), "text": c.text, "bboxes": c.bboxes,
        "dense_rank": c.dense_rank, "dense_score": c.dense_score, "bm25_rank": c.bm25_rank,
        "bm25_score": c.bm25_score, "rrf_score": c.rrf_score, "rerank_score": c.rerank_score,
        "rerank_prob": c.rerank_prob, "in_context": context_n is not None, "context_n": context_n, "cited": cited,
    }


def select_context(ranked: List[ScoredChunk], top_k: int, token_limit: int) -> List[ScoredChunk]:
    out, budget = [], token_limit
    for c in ranked[:top_k]:
        if c.token_count > budget and out:
            break
        out.append(c)
        budget -= c.token_count
    return out


class QueryService:
    def __init__(self, retriever: HybridRetriever, reranker=None, llm=None):
        self.retriever = retriever
        self.reranker = reranker
        self.llm = llm
        self.gate = AnswerabilityChecker()

    async def rewrite_query(self, query: str, history: List[ConversationTurn]) -> Dict:
        if not needs_rewrite(query, history):
            return {"rewritten": query, "method": "none"}
        if self.llm is not None and self.llm.available:
            try:
                res = await self.llm.generate(build_rewrite_prompt(query, history), REWRITE_SYSTEM_PROMPT,
                                              tier="fast", max_tokens=settings.rewrite_max_output_tokens,
                                              timeout=settings.rewrite_timeout_seconds)
                text = " ".join(res.text.strip().strip('"').split())
                if 3 <= len(text) <= 400:
                    return {"rewritten": text, "method": "llm"}
            except Exception as e:  # noqa: BLE001
                logger.warning("query_rewrite_failed", error=str(e)[:200])
        return {"rewritten": build_effective_query(query, history), "method": "heuristic"}

    async def run_streaming(self, query: str, history: List[ConversationTurn],
                            doc_ids: Optional[List[str]] = None,
                            rerank: Optional[bool] = None) -> AsyncGenerator[StreamEvent, None]:
        t_start = time.perf_counter()
        timings: Dict[str, float] = {}
        history = trim_history(history)
        use_rerank = (settings.reranker_enabled if rerank is None else rerank) and self.reranker is not None

        # 1. Follow-up rewrite
        rewritten = query
        if needs_rewrite(query, history):
            yield StreamEvent(type="status", data={"stage": "rewriting", "message": "Resolving follow-up question…"})
            t = time.perf_counter()
            rw = await self.rewrite_query(query, history)
            timings["rewrite_ms"] = _ms(t)
            rewritten = rw["rewritten"]
            yield StreamEvent(type="rewrite", data={"original": query, **rw})
        else:
            timings["rewrite_ms"] = 0.0

        # 2. Hybrid retrieval + RRF
        yield StreamEvent(type="status", data={"stage": "retrieving", "message": "Searching dense + BM25 indexes…"})
        fused, rt = await run_in_threadpool(self.retriever.retrieve, rewritten, doc_ids)
        timings.update({k: round(v, 1) for k, v in rt.items()})

        # 3. Rerank the top RRF candidates
        if use_rerank and fused:
            yield StreamEvent(type="status", data={"stage": "reranking", "message": "Reranking passages…"})
            t = time.perf_counter()
            head = fused[:settings.rerank_candidates]
            reranked = await run_in_threadpool(self.reranker.rerank, rewritten, head)
            ranked = reranked + fused[settings.rerank_candidates:]
            timings["rerank_ms"] = _ms(t)
        else:
            ranked = fused
            timings["rerank_ms"] = 0.0

        display = ranked[:settings.retrieval_display_k]
        context = select_context(ranked, settings.context_top_k, settings.context_token_limit)
        ctx_n = {c.chunk_id: i for i, c in enumerate(context, start=1)}
        assessment = self.gate.evaluate(ranked)

        def chunks_payload(cited_ids=()):
            return [chunk_payload(c, i, ctx_n.get(c.chunk_id), c.chunk_id in cited_ids)
                    for i, c in enumerate(display, start=1)]

        yield StreamEvent(type="retrieval", data={"chunks": chunks_payload(), "evidence_score": assessment.evidence_score,
                                                  "evidence_signal": assessment.signal})

        base_final = {"rewritten_query": rewritten if rewritten != query else "", "evidence_score": assessment.evidence_score,
                      "evidence_signal": assessment.signal, "invalid_citations_stripped": 0, "model": None}

        # 4. Evidence gate
        if not assessment.is_sufficient or not context:
            timings["e2e_ms"] = _ms(t_start)
            yield StreamEvent(type="final", data={**base_final, "answer": "", "citations": [], "chunks": chunks_payload(),
                                                  "confidence": "ABSTAIN", "abstained": True,
                                                  "abstain_reason": assessment.reason, "timings": timings,
                                                  "ttft_ms": None})
            yield StreamEvent(type="done", data={})
            return

        if self.llm is None or not self.llm.available:
            yield StreamEvent(type="error", data={"message": "No GEMINI_API_KEY configured; retrieval results are shown."})
            timings["e2e_ms"] = _ms(t_start)
            yield StreamEvent(type="final", data={**base_final, "answer": "", "citations": [], "chunks": chunks_payload(),
                                                  "confidence": "ABSTAIN", "abstained": True,
                                                  "abstain_reason": "LLM not configured.", "timings": timings})
            yield StreamEvent(type="done", data={})
            return

        # 5. Grounded generation (streamed)
        yield StreamEvent(type="status", data={"stage": "generating", "message": "Generating answer…"})
        prompt = build_grounded_prompt(query if rewritten == query else f"{query}\n(Interpreted as: {rewritten})",
                                       context, history)
        t_llm = time.perf_counter()
        full, held, released = "", "", False
        meta: Dict = {}
        try:
            async for delta in self.llm.generate_streaming(prompt, SYSTEM_PROMPT, tier="fast", meta=meta):
                if "ttft_ms" not in timings:
                    timings["ttft_ms"] = _ms(t_llm)
                full += delta
                if released:
                    yield StreamEvent(type="token", data={"text": delta})
                    continue
                held += delta
                # Hold back the opening characters so an abstain sentinel never flashes in the UI.
                s = held.lstrip()
                if s.startswith(ABSTAIN_SENTINEL) or ABSTAIN_SENTINEL.startswith(s):
                    continue
                released = True
                yield StreamEvent(type="token", data={"text": held})
            if not released and held and not held.lstrip().startswith(ABSTAIN_SENTINEL):
                yield StreamEvent(type="token", data={"text": held})
        except Exception as e:  # noqa: BLE001
            logger.error("llm_stream_failed", error=str(e)[:300])
            timings["llm_ms"] = _ms(t_llm)
            timings["e2e_ms"] = _ms(t_start)
            yield StreamEvent(type="error", data={"message": "The language model is unavailable right now "
                                                             "(all keys/models failed). Retrieved passages are shown."})
            yield StreamEvent(type="final", data={**base_final, "answer": "", "citations": [], "chunks": chunks_payload(),
                                                  "confidence": "ABSTAIN", "abstained": True,
                                                  "abstain_reason": "LLM unavailable.", "timings": timings})
            yield StreamEvent(type="done", data={})
            return
        timings["llm_ms"] = _ms(t_llm)
        timings.setdefault("ttft_ms", timings["llm_ms"])

        # 6. Citation validation + confidence
        val = CitationValidator.validate(full, context)
        conf = ConfidenceClassifier.classify(assessment.evidence_score if assessment.signal == "rerank" else 0.6,
                                             len(val.citations), val.uncited_sentences, val.invalid_markers,
                                             val.abstained)
        timings["e2e_ms"] = _ms(t_start)
        yield StreamEvent(type="final", data={
            **base_final,
            "answer": val.answer,
            "citations": [c.__dict__ for c in val.citations],
            "chunks": chunks_payload(set(val.cited_chunk_ids)),
            "confidence": conf,
            "abstained": val.abstained,
            "abstain_reason": ("The model found no support for an answer in the retrieved passages."
                               if val.abstained else None),
            "invalid_citations_stripped": val.invalid_markers,
            "uncited_sentences": val.uncited_sentences,
            "model": meta.get("model"),
            "timings": timings,
        })
        yield StreamEvent(type="done", data={})
