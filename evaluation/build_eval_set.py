"""Builds evaluation/eval_set.jsonl: answerable questions generated from sampled chunks (gold = filename +
page range of the source chunk) plus hand-written unanswerable questions. Every item is marked
"reviewed": false so a human can check it.

    python -m evaluation.build_eval_set --answerable 20 --seed 7
"""
import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.providers.gemini_provider import GeminiProvider  # noqa: E402
from ingestion.store import Store  # noqa: E402

OUT = ROOT / "evaluation" / "eval_set.jsonl"

UNANSWERABLE = [
    "Who won the 2022 FIFA World Cup final?",
    "What is the current market price of one Bitcoin?",
    "How do I configure an ingress controller in Kubernetes?",
    "Which actor played the lead role in the movie Inception?",
    "What are the opening hours of the Taj Mahal on Fridays?",
    "Who is the current Chief Minister of Karnataka?",
    "What is the best recipe for a Hyderabadi biryani?",
]

GEN_SYSTEM = """You write evaluation questions for a document question-answering system.
Given one passage from a book, write ONE specific factual question that can be answered from this passage alone,
and a short reference answer (1-2 sentences) taken from the passage.
Rules: the question must make sense without seeing the passage (no "this passage", "the figure", "the author");
name the concept explicitly; avoid yes/no questions; avoid questions about exercise numbers or figure numbers.
Return JSON: {"question": "...", "answer": "...", "usable": true}. Set "usable": false if the passage is only
front matter, an index, a list of references, exercises without content, or too garbled to ask about."""


def sample_chunks(store: Store, n: int, seed: int, min_ocr: int):
    rng = random.Random(seed)
    rows = store.conn.execute(
        """SELECT c.chunk_id, c.doc_id, c.page_start, c.page_end, c.text, c.has_ocr, c.token_count,
                  d.filename, d.title, d.page_count, d.force_ocr
           FROM chunks c JOIN documents d USING (doc_id) WHERE d.status='done' AND c.token_count >= 250
           ORDER BY c.chunk_id""").fetchall()
    # Skip the first/last 4% of each book (front matter, index, references).
    rows = [r for r in rows if 0.04 * r["page_count"] < r["page_start"] < 0.96 * r["page_count"]]
    by_doc = {}
    for r in rows:
        by_doc.setdefault(r["filename"], []).append(r)
    # Fully OCR'd (scanned) documents get guaranteed questions; stray OCR'd figure pages in textbooks don't.
    ocr_docs = sorted({r["filename"] for r in rows if r["force_ocr"]})
    picks, used = [], set()
    for f in ocr_docs:  # guarantee questions whose answers live on OCR'd pages
        pool = [r for r in by_doc[f] if r["has_ocr"]]
        for r in rng.sample(pool, min(min_ocr, len(pool))):
            picks.append(r)
            used.add(r["chunk_id"])
    docs = sorted(by_doc)
    i = 0
    while len(picks) < n * 2 and any(by_doc.values()):  # over-sample: some chunks get rejected
        f = docs[i % len(docs)]
        i += 1
        cand = [r for r in by_doc[f] if r["chunk_id"] not in used]
        if not cand:
            continue
        r = rng.choice(cand)
        used.add(r["chunk_id"])
        picks.append(r)
    return picks


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answerable", type=int, default=20)
    ap.add_argument("--unanswerable", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--min-ocr", type=int, default=3)
    ap.add_argument("--tier", choices=["heavy", "fast"], default="heavy",
                    help="Gemini tier used to write questions (fast when the heavy tier is out of quota)")
    args = ap.parse_args()

    store = Store()
    llm = GeminiProvider()
    picks = sample_chunks(store, args.answerable, args.seed, args.min_ocr)
    items = []
    for r in picks:
        if len(items) >= args.answerable:
            break
        prompt = f"Book: {r['title']}\nPassage:\n\"\"\"\n{r['text']}\n\"\"\""
        try:
            res = await llm.generate(prompt, GEN_SYSTEM, tier=args.tier, max_tokens=400, json_mode=True, timeout=40)
            q = json.loads(res.text)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {r['chunk_id']}: {e}")
            continue
        if not q.get("usable") or not q.get("question"):
            print(f"  unusable chunk {r['filename']} p.{r['page_start']}")
            continue
        items.append({
            "id": f"a{len(items) + 1:02d}", "question": q["question"].strip(), "answerable": True,
            "reference_answer": q.get("answer", "").strip(), "gold_filename": r["filename"],
            "gold_page": r["page_start"], "gold_pages": list(range(r["page_start"], r["page_end"] + 1)),
            "gold_chunk_id": r["chunk_id"], "from_ocr_page": bool(r["has_ocr"]),
            "generated_by": res.model, "reviewed": False,
        })
        print(f"  {items[-1]['id']} {r['filename']} p.{r['page_start']}: {items[-1]['question']}")
    if len(items) < args.answerable:
        print(f"\nOnly {len(items)}/{args.answerable} answerable questions generated (LLM quota?); "
              f"keeping the existing {OUT.name} unchanged.")
        sys.exit(1)
    for i, q in enumerate(UNANSWERABLE[:args.unanswerable], start=1):
        items.append({"id": f"u{i:02d}", "question": q, "answerable": False, "reference_answer": None,
                      "gold_filename": None, "gold_page": None, "gold_pages": [], "gold_chunk_id": None,
                      "from_ocr_page": False, "generated_by": "hand-written", "reviewed": False})
    OUT.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in items) + "\n", encoding="utf-8")
    n_ans = sum(x["answerable"] for x in items)
    print(f"\nWrote {len(items)} questions ({n_ans} answerable, {len(items) - n_ans} unanswerable, "
          f"{sum(x['from_ocr_page'] for x in items)} from OCR pages) to {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
