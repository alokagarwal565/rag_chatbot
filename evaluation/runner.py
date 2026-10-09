"""End-to-end evaluation against the running API (SSE), plus an in-process retrieval ablation.

    python -m evaluation.runner [--api http://127.0.0.1:7860] [--no-judge] [--no-ablation]

Metrics
- Recall@1/5/10, MRR@10: rank of the first retrieved chunk (final order shown to the user) from the gold
  file whose page range covers a gold page.
- Latency: client-measured time to first answer token and to the final event (sequential queries, one
  warm-up query excluded), plus server-side per-stage timings.
- Citation accuracy: share of citations whose page matches the gold page, or that the judge says
  support the claim they are attached to.
- Hallucination rate: share of non-abstained answers with >= 1 claim the judge finds unsupported by the
  retrieved sources (answers given to unanswerable questions count as hallucinations).
- Correct / false abstention on unanswerable / answerable questions, and an evidence-threshold sweep.

Writes evaluation/report.json, evaluation/report.md and evaluation/runs/<timestamp>.json.
"""
import argparse
import asyncio
import datetime as dt
import json
import platform
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from evaluation.judge import judge_answer  # noqa: E402
from evaluation.metrics import first_hit_rank, mrr_at_k, percentile, recall_at_k, threshold_sweep  # noqa: E402

EVAL_SET = ROOT / "evaluation" / "eval_set.jsonl"
REPORT_JSON = ROOT / "evaluation" / "report.json"
REPORT_MD = ROOT / "evaluation" / "report.md"
RUNS = ROOT / "evaluation" / "runs"


async def ask(client: httpx.AsyncClient, api: str, question: str) -> dict:
    t0 = time.perf_counter()
    ttft = None
    events, final, ev = [], None, None
    tokens = []
    async with client.stream("POST", f"{api}/api/v1/query", json={"question": question}) as r:
        r.raise_for_status()
        async for line in r.aiter_lines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:])
                events.append(ev)
                if ev == "token":
                    if ttft is None:
                        ttft = (time.perf_counter() - t0) * 1000
                    tokens.append(data["text"])
                elif ev == "final":
                    final = data
                elif ev in ("fast_path", "decline"):
                    final = {"answer": data["message"], "abstained": True, "chunks": [], "citations": [],
                             "timings": {}, "evidence_score": 0.0, "routed": ev}
                elif ev == "done":
                    break
    e2e = (time.perf_counter() - t0) * 1000
    return {"final": final or {}, "client_ttft_ms": ttft, "client_e2e_ms": e2e, "events": events,
            "streamed_text": "".join(tokens)}


def retrieval_ablation(items):
    """Recall/MRR with and without the reranker, computed in-process (no LLM calls)."""
    from app.config import settings
    from app.providers.fastembed_provider import CrossEncoderReranker
    from app.services.retriever import HybridRetriever
    from ingestion.embedder import get_embedder
    from ingestion.store import Store
    from ingestion.vector_store import VectorStore

    retr = HybridRetriever(Store(), VectorStore(), get_embedder())
    rr = CrossEncoderReranker()
    out = {"rrf_only": [], "rrf_rerank": [], "dense_only": [], "bm25_only": []}
    for q in items:
        if not q["answerable"]:
            continue
        fused, _ = retr.retrieve(q["question"])
        as_dict = lambda cs: [{"filename": c.filename, "page_start": c.page_start, "page_end": c.page_end} for c in cs]  # noqa: E731
        out["rrf_only"].append(first_hit_rank(as_dict(fused), q["gold_filename"], q["gold_pages"]))
        head = rr.rerank(q["question"], fused[:settings.rerank_candidates])
        out["rrf_rerank"].append(first_hit_rank(as_dict(head + fused[settings.rerank_candidates:]),
                                                q["gold_filename"], q["gold_pages"]))
        dense = sorted([c for c in fused if c.dense_rank], key=lambda c: c.dense_rank)
        bm25 = sorted([c for c in fused if c.bm25_rank], key=lambda c: c.bm25_rank)
        out["dense_only"].append(first_hit_rank(as_dict(dense), q["gold_filename"], q["gold_pages"]))
        out["bm25_only"].append(first_hit_rank(as_dict(bm25), q["gold_filename"], q["gold_pages"]))
    return {k: {"recall_at_1": round(recall_at_k(v, 1), 3), "recall_at_5": round(recall_at_k(v, 5), 3),
                "recall_at_10": round(recall_at_k(v, 10), 3), "mrr_at_10": round(mrr_at_k(v), 3)}
            for k, v in out.items()}


def _r(v, d=1):
    return None if v is None else round(v, d)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:7860")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--no-ablation", action="store_true")
    args = ap.parse_args()

    items = [json.loads(l) for l in EVAL_SET.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{len(items)} questions from {EVAL_SET.name}")
    results = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        h = (await client.get(f"{args.api}/api/v1/health")).json()
        print(f"API: {h}")
        await ask(client, args.api, "What is the function of chlorophyll in plants?")  # warm-up, not counted
        for q in items:
            res = await ask(client, args.api, q["question"])
            f = res["final"]
            rank = first_hit_rank(f.get("chunks", []), q["gold_filename"], q["gold_pages"]) if q["answerable"] else None
            row = {"id": q["id"], "question": q["question"], "answerable": q["answerable"],
                   "gold_filename": q["gold_filename"], "gold_page": q["gold_page"], "gold_pages": q["gold_pages"],
                   "from_ocr_page": q.get("from_ocr_page", False), "hit_rank": rank,
                   "abstained": bool(f.get("abstained")), "answer": f.get("answer", ""),
                   "citations": f.get("citations", []), "evidence_score": f.get("evidence_score"),
                   "timings": f.get("timings", {}), "client_ttft_ms": _r(res["client_ttft_ms"]),
                   "e2e_ms": _r(res["client_e2e_ms"]), "model": f.get("model"),
                   "invalid_citations_stripped": f.get("invalid_citations_stripped", 0),
                   "context": [c for c in f.get("chunks", []) if c.get("in_context")]}
            results.append(row)
            print(f"  {q['id']} hit@{rank} abstained={row['abstained']} cites={len(row['citations'])} "
                  f"e2e={row['e2e_ms']:.0f}ms ttft={row['client_ttft_ms']} :: {q['question'][:70]}")

    # ---- LLM judge (claims vs sources)
    if not args.no_judge:
        from app.providers.gemini_provider import GeminiProvider
        llm = GeminiProvider()
        for row in results:
            if row["abstained"] or not row["answer"]:
                continue
            try:
                row["judge"] = await judge_answer(llm, row["question"], row["answer"], row["context"])
            except Exception as e:  # noqa: BLE001
                row["judge"] = {"error": str(e)[:200]}
            j = row["judge"]
            print(f"  judge {row['id']}: claims={j.get('n_claims')} unsupported={j.get('n_unsupported')}")

    # ---- metrics
    ans = [r for r in results if r["answerable"]]
    una = [r for r in results if not r["answerable"]]
    ranks = [r["hit_rank"] for r in ans]
    answered = [r for r in results if not r["abstained"]]

    cit_total, cit_ok = 0, 0
    for r in ans:
        r["citation_accuracy"] = None
        if r["abstained"] or not r["citations"]:
            continue
        sup = {s["n"]: s.get("supports") for s in r.get("judge", {}).get("sources", [])}
        ok = 0
        for c in r["citations"]:
            gold_hit = c["filename"] == r["gold_filename"] and set(r["gold_pages"]) & set(range(c["page_start"], c["page_end"] + 1))
            if gold_hit or sup.get(c["n"]):
                ok += 1
        cit_total += len(r["citations"])
        cit_ok += ok
        r["citation_accuracy"] = ok / len(r["citations"])

    judged = [r for r in answered if "judge" in r and "error" not in r["judge"]]
    for r in results:
        r["unsupported_claims"] = r.get("judge", {}).get("n_unsupported")
    halluc_answers = sum(1 for r in judged if r["judge"]["n_unsupported"] > 0 or not r["answerable"])
    n_claims = sum(r["judge"]["n_claims"] for r in judged)
    n_unsup = sum(r["judge"]["n_unsupported"] for r in judged)

    def stage(name):
        return [r["timings"].get(name) for r in results if r["timings"].get(name) is not None]

    stages = ["rewrite_ms", "embed_ms", "dense_ms", "lexical_ms", "fusion_ms", "rerank_ms", "ttft_ms", "llm_ms", "e2e_ms"]
    e2e = [r["e2e_ms"] for r in results]
    ttft = [r["client_ttft_ms"] for r in results if r["client_ttft_ms"] is not None]
    sweep = threshold_sweep([r["evidence_score"] or 0 for r in ans], [r["evidence_score"] or 0 for r in una],
                            [0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5])

    from app.config import settings
    report = {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "hardware": f"{platform.processor() or 'CPU'} · {__import__('os').cpu_count()} logical cores · no GPU",
        "eval_set": {"file": "evaluation/eval_set.jsonl", "reviewed": all(q.get("reviewed") for q in items),
                     "note": "LLM-generated questions, not yet human-reviewed"},
        "index": {"documents": h.get("documents"), "chunks": h.get("chunks"), "vectors": h.get("vectors")},
        "n_questions": len(results), "n_answerable": len(ans), "n_unanswerable": len(una),
        "config": {"llm": settings.gemini_model_fast, "reranker": settings.reranker_model if settings.reranker_enabled else None,
                   "rerank_candidates": settings.rerank_candidates, "abstain_threshold": settings.abstain_threshold,
                   "context_top_k": settings.context_top_k, "dense_top_k": settings.dense_top_k,
                   "lexical_top_k": settings.lexical_top_k},
        "retrieval": {"recall_at_1": round(recall_at_k(ranks, 1), 3), "recall_at_5": round(recall_at_k(ranks, 5), 3),
                      "recall_at_10": round(recall_at_k(ranks, 10), 3), "mrr_at_10": round(mrr_at_k(ranks), 3),
                      "ocr_questions": len([r for r in ans if r["from_ocr_page"]]),
                      "ocr_recall_at_5": round(recall_at_k([r["hit_rank"] for r in ans if r["from_ocr_page"]], 5), 3)},
        "generation": {
            "citation_accuracy": round(cit_ok / cit_total, 3) if cit_total else None,
            "citations_checked": cit_total,
            "hallucination_rate": round(halluc_answers / len(judged), 3) if judged else None,
            "unsupported_claim_rate": round(n_unsup / n_claims, 3) if n_claims else None,
            "claims_judged": n_claims,
            "answer_rate_on_answerable": round(sum(not r["abstained"] for r in ans) / len(ans), 3) if ans else None,
            "false_abstention_rate": round(sum(r["abstained"] for r in ans) / len(ans), 3) if ans else None,
            "correct_abstention_rate": round(sum(r["abstained"] for r in una) / len(una), 3) if una else None,
            "invalid_citations_stripped": sum(r["invalid_citations_stripped"] for r in results),
        },
        "latency": {
            "e2e_p50": _r(percentile(e2e, 50)), "e2e_p95": _r(percentile(e2e, 95)), "e2e_max": _r(max(e2e)),
            "ttft_p50": _r(percentile(ttft, 50)), "ttft_p95": _r(percentile(ttft, 95)),
            "answered_e2e_p95": _r(percentile([r["e2e_ms"] for r in answered], 95)),
            "stage_p50": {s: _r(percentile(stage(s), 50)) for s in stages},
            "stage_p95": {s: _r(percentile(stage(s), 95)) for s in stages},
        },
        "threshold_sweep": sweep,
        "per_question": [{k: r.get(k) for k in ("id", "question", "answerable", "gold_filename", "gold_page",
                                                 "from_ocr_page", "hit_rank", "abstained", "citation_accuracy",
                                                 "unsupported_claims", "evidence_score", "e2e_ms", "client_ttft_ms")}
                         for r in results],
    }
    if not args.no_ablation:
        print("Running retrieval ablation in-process…")
        report["retrieval_ablation"] = retrieval_ablation(items)

    RUNS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    (RUNS / f"{stamp}.json").write_text(json.dumps({"report": report, "results": results}, indent=1, ensure_ascii=False),
                                        encoding="utf-8")
    REPORT_JSON.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(render_md(report), encoding="utf-8")
    print(render_md(report))


def render_md(r: dict) -> str:
    g, ret, lat = r["generation"], r["retrieval"], r["latency"]
    pct = lambda v: "—" if v is None else f"{v * 100:.1f}%"  # noqa: E731
    ms = lambda v: "—" if v is None else f"{v / 1000:.2f} s" if v >= 1000 else f"{v:.0f} ms"  # noqa: E731
    lines = [
        "# Granth evaluation report", "",
        f"Generated {r['generated_at']} on {r['hardware']}. {r['n_questions']} questions "
        f"({r['n_answerable']} answerable, {r['n_unanswerable']} unanswerable); {r['eval_set']['note']}. "
        f"Index searched: {r.get('index', {}).get('documents')} PDF(s), {r.get('index', {}).get('chunks')} chunks.", "",
        f"Config: LLM `{r['config']['llm']}`, reranker `{r['config']['reranker']}` over the top "
        f"{r['config']['rerank_candidates']} RRF candidates, abstain threshold {r['config']['abstain_threshold']}, "
        f"top-{r['config']['context_top_k']} chunks to the LLM.", "",
        "## Retrieval", "", "| Metric | Value |", "|---|---|",
        f"| Recall@1 | {pct(ret['recall_at_1'])} |", f"| Recall@5 | {pct(ret['recall_at_5'])} |",
        f"| Recall@10 | {pct(ret['recall_at_10'])} |", f"| MRR@10 | {ret['mrr_at_10']:.3f} |",
        f"| Recall@5 on questions from OCR'd pages ({ret['ocr_questions']}) | {pct(ret['ocr_recall_at_5'])} |", "",
    ]
    if "retrieval_ablation" in r:
        lines += ["### Ablation (same questions, in-process, no LLM)", "",
                  "| Pipeline | R@1 | R@5 | R@10 | MRR@10 |", "|---|---|---|---|---|"]
        for k, v in r["retrieval_ablation"].items():
            lines.append(f"| {k} | {pct(v['recall_at_1'])} | {pct(v['recall_at_5'])} | {pct(v['recall_at_10'])} | {v['mrr_at_10']:.3f} |")
        lines.append("")
    lines += [
        "## Generation", "", "| Metric | Value |", "|---|---|",
        f"| Citation accuracy | {pct(g['citation_accuracy'])} ({g['citations_checked']} citations) |",
        f"| Hallucination rate (answers with ≥1 unsupported claim) | {pct(g['hallucination_rate'])} |",
        f"| Unsupported claims / all judged claims | {pct(g['unsupported_claim_rate'])} ({g['claims_judged']} claims) |",
        f"| Answered (answerable questions) | {pct(g['answer_rate_on_answerable'])} |",
        f"| False abstention (answerable) | {pct(g['false_abstention_rate'])} |",
        f"| Correct abstention (unanswerable) | {pct(g['correct_abstention_rate'])} |",
        f"| Invalid citation markers stripped | {g['invalid_citations_stripped']} |", "",
        "## Latency (client-measured, sequential, after one warm-up query)", "",
        "| Metric | p50 | p95 |", "|---|---|---|",
        f"| End-to-end (question → final event) | {ms(lat['e2e_p50'])} | {ms(lat['e2e_p95'])} |",
        f"| Time to first answer token | {ms(lat['ttft_p50'])} | {ms(lat['ttft_p95'])} |", "",
        "Server-side stages:", "", "| Stage | p50 | p95 |", "|---|---|---|",
    ]
    for s in lat["stage_p50"]:
        lines.append(f"| {s.replace('_ms', '')} | {ms(lat['stage_p50'][s])} | {ms(lat['stage_p95'][s])} |")
    lines += ["", "## Evidence-gate threshold sweep", "", "| Threshold | Correct abstention | False abstention |",
              "|---|---|---|"]
    for row in r["threshold_sweep"]:
        lines.append(f"| {row['threshold']} | {pct(row['correct_abstention'])} | {pct(row['false_abstention'])} |")
    lines += ["", "## Per question", "", "| ID | Hit rank | Abstained | Cit. acc. | Unsupported | E2E | Question |",
              "|---|---|---|---|---|---|---|"]
    for q in r["per_question"]:
        lines.append(f"| {q['id']} | {q['hit_rank'] if q['answerable'] else 'n/a'} | {q['abstained']} | "
                     f"{pct(q['citation_accuracy'])} | {q['unsupported_claims'] if q['unsupported_claims'] is not None else '—'} | "
                     f"{ms(q['e2e_ms'])} | {q['question']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    asyncio.run(main())
