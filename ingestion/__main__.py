"""CLI: python -m ingestion [--only NAME ...] [--force] [--workers N] [--status]"""
import argparse
import json
import sys
import time


def print_status() -> None:
    from ingestion.store import Store
    from ingestion.vector_store import VectorStore
    store = Store()
    rows = store.list_documents()
    print(f"{'file':<46} {'pages':>5} {'native':>6} {'ocr':>5} {'chunks':>6} {'lang':>4}  {'status':<8} stage timings (s)")
    for r in rows:
        st = json.loads(r["stage_timings"] or "{}")
        tim = " ".join(f"{k}={v:.0f}" for k, v in st.items())
        print(f"{r['filename'][:46]:<46} {r['page_count'] or 0:>5} {r['native_pages'] or 0:>6} {r['ocr_pages'] or 0:>5} "
              f"{r['chunk_count'] or 0:>6} {r['language'] or '-':>4}  {r['status']:<8} {tim}")
    t = store.totals()
    print(f"\nTOTAL (done): {t['documents']} docs, {t['pages']} pages ({t['native_pages']} native, "
          f"{t['ocr_pages']} OCR), {t['chunks']} chunks, {VectorStore().count()} vectors in Chroma")


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m ingestion", description=__doc__)
    ap.add_argument("--only", nargs="*", help="substring(s) of PDF filenames to ingest")
    ap.add_argument("--force", action="store_true", help="re-extract and re-embed even if up to date")
    ap.add_argument("--workers", type=int, default=None, help="OCR worker processes (max 3)")
    ap.add_argument("--status", action="store_true", help="print the status table and exit")
    args = ap.parse_args()

    if args.status:
        print_status()
        return 0

    from ingestion import config
    from ingestion.pipeline import Pipeline
    workers = max(1, min(3, args.workers or config.OCR_WORKERS))
    pdfs = sorted(config.PDF_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {config.PDF_DIR}. Run: python scripts/download_corpus.py")
        return 1
    t0 = time.time()
    pipe = Pipeline(workers=workers, force=args.force)
    print(f"Ingesting {len(pdfs)} PDF(s) from {config.PDF_DIR} · OCR backend={pipe.ocr_backend} workers={workers}")
    results = pipe.run(only=args.only)
    failed = [r for r in results if r.status == "failed"]
    print(f"\nFinished in {time.time() - t0:.1f}s: {sum(r.status == 'done' for r in results)} ingested, "
          f"{sum(r.status == 'skipped' for r in results)} up to date, {len(failed)} failed\n")
    print_status()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
