"""Ingestion pipeline: PDF -> extract/OCR -> clean -> chunk -> embed -> Chroma + SQLite.

Idempotent and resumable:
- A document is identified by the sha256 of its bytes (doc_id = first 16 hex chars). A file whose
  document is already `done` with a matching vector count is skipped. A changed file replaces the old one.
- Every extracted / OCR'd page is written to the `pages` table as soon as it is ready, so an
  interrupted run picks up where it stopped (OCR is the expensive part).
- Chunking, embedding and indexing are rebuilt per document (deterministic, so the result is identical).
"""
import hashlib
import json
import time
import faulthandler
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pymupdf as fitz
from tqdm import tqdm

from ingestion import config
from ingestion.chunker import chunk_document
from ingestion.clean import _key, clean_document, document_language
from ingestion.extract import (Block, PageData, is_native, large_image_rects, mean_conf, native_blocks,
                               ocr_lines_to_blocks)
from ingestion.ocr import backend_name, ocr_task
from ingestion.store import Store
from ingestion.vector_store import VectorStore

PAGE_SAVE_BATCH = 50


def _worker_init():
    """OCR worker setup: native-crash tracebacks to a log file, and no thread oversubscription."""
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    try:
        import cv2
        cv2.setNumThreads(1)
    except Exception:  # noqa: BLE001
        pass
    log = open(config.DATA_DIR / f"ocr_worker_{os.getpid()}.log", "w")
    faulthandler.enable(file=log)
EMBED_PROGRESS_BATCH = 64


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest() -> Dict[str, dict]:
    p = config.PDF_DIR / "manifest.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {e["filename"]: e for e in data.values()}


def select_evenly(items: list, cap: int) -> list:
    if cap <= 0:
        return []
    if len(items) <= cap:
        return items
    if cap == 1:
        return [items[0]]
    idx = sorted({round(k * (len(items) - 1) / (cap - 1)) for k in range(cap)})
    return [items[i] for i in idx]


def _page_row(p: PageData) -> dict:
    return {"page_no": p.page_no, "width": p.width, "height": p.height, "method": p.method,
            "char_count": p.char_count, "ocr_conf": p.ocr_conf, "error": p.error,
            "blocks_json": json.dumps([b.to_json() for b in p.blocks], ensure_ascii=False)}


def _row_to_page(r) -> PageData:
    blocks = [Block.from_json(b) for b in json.loads(r["blocks_json"])]
    return PageData(r["page_no"], r["width"], r["height"], r["method"], blocks, r["ocr_conf"], r["error"])


@dataclass
class DocResult:
    filename: str
    status: str
    pages: int = 0
    ocr_pages: int = 0
    chunks: int = 0
    seconds: float = 0.0
    note: str = ""


class Pipeline:
    def __init__(self, workers: int = config.OCR_WORKERS, force: bool = False, quiet: bool = False):
        config.ensure_dirs()
        self.store = Store()
        self.vectors = VectorStore()
        self.workers = workers
        self.force = force
        self.quiet = quiet
        self._pool: Optional[ProcessPoolExecutor] = None
        self._embedder = None
        self.ocr_backend = backend_name()

    @property
    def embedder(self):
        if self._embedder is None:
            from ingestion.embedder import get_embedder
            self._embedder = get_embedder()
        return self._embedder

    @property
    def pool(self) -> ProcessPoolExecutor:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=self.workers, initializer=_worker_init)
        return self._pool

    def close(self):
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None

    def _ocr_results(self, jobs: list):
        """Yields OCR results for `jobs`, surviving worker crashes (native faults / OOM kill a process and
        break the whole pool). After a crash the remaining jobs are retried on a fresh pool; after a second
        crash they run one at a time so the job that kills its worker is identified and skipped."""
        pending = dict(enumerate(jobs))
        crashes = 0
        while pending:
            serial = crashes >= 2
            try:
                if serial:
                    i, job = next(iter(pending.items()))
                    with ProcessPoolExecutor(max_workers=1, initializer=_worker_init) as one:
                        r = one.submit(ocr_task, job).result()
                    del pending[i]
                    yield r
                    continue
                futs = {self.pool.submit(ocr_task, j): i for i, j in pending.items()}
                for fut in as_completed(futs):
                    r = fut.result()
                    del pending[futs[fut]]
                    yield r
            except BrokenProcessPool:
                crashes += 1
                self.close()
                if serial:  # this exact job crashes the worker: record it and move on
                    i, job = next(iter(pending.items()))
                    del pending[i]
                    self._log(f"  OCR job crashed its worker twice, skipped: page {job[1]} ({job[4]})")
                    yield {"page_no": job[1], "kind": job[4], "clip": job[3], "lines": [], "backend": job[5],
                           "error": "worker crashed on this page"}
                else:
                    self._log(f"  OCR worker crashed ({len(pending)} jobs left); restarting the pool")

    # ------------------------------------------------------------------ run
    def run(self, only: Optional[List[str]] = None) -> List[DocResult]:
        pdfs = sorted(config.PDF_DIR.glob("*.pdf"))
        if only:
            pdfs = [p for p in pdfs if any(o.lower() in p.name.lower() for o in only)]
        manifest = load_manifest()
        run_id = self.store.start_run(len(pdfs))
        totals: Dict[str, float] = {}
        results: List[DocResult] = []
        status, err = "done", None
        try:
            for pdf in pdfs:
                res = self.ingest(pdf, manifest.get(pdf.name, {}), totals)
                results.append(res)
                self._log(f"  {res.status:<8} {res.filename}  pages={res.pages} ocr={res.ocr_pages} "
                          f"chunks={res.chunks} {res.seconds:.1f}s {res.note}")
        except KeyboardInterrupt:
            status, err = "interrupted", "KeyboardInterrupt"
            raise
        except Exception as e:  # noqa: BLE001
            status, err = "failed", repr(e)
            raise
        finally:
            self.store.finish_run(run_id, status, sum(r.status in ("done", "skipped") for r in results),
                                  {k: round(v, 2) for k, v in totals.items()}, err)
            self.close()
        return results

    def _log(self, msg: str):
        if not self.quiet:
            tqdm.write(msg)

    # ------------------------------------------------------------------ one document
    def ingest(self, pdf: Path, meta: dict, totals: Dict[str, float]) -> DocResult:
        t0 = time.time()
        sha = sha256_file(pdf)
        doc_id = sha[:16]
        force_ocr = bool(meta.get("force_ocr"))

        existing = self.store.get_document_by_filename(pdf.name)
        if existing is not None and existing["doc_id"] != doc_id:
            self._log(f"  {pdf.name}: file changed, replacing previous version")
            self.vectors.delete_doc(existing["doc_id"])
            self.store.delete_document(existing["doc_id"])
            existing = None
        if (existing is not None and existing["status"] == "done" and not self.force
                and self.vectors.count_doc(doc_id) == existing["chunk_count"]):
            return DocResult(pdf.name, "skipped", existing["page_count"], existing["ocr_pages"],
                             existing["chunk_count"], time.time() - t0, "(up to date)")
        if self.force and existing is not None:
            self.vectors.delete_doc(doc_id)
            self.store.delete_document(doc_id)

        with fitz.open(pdf) as doc:
            n_pages = doc.page_count
        self.store.upsert_document(
            doc_id=doc_id, filename=pdf.name, title=meta.get("title") or pdf.stem, authors=meta.get("authors"),
            source=meta.get("source", "local"), source_url=meta.get("details_url") or meta.get("source_url"),
            license=meta.get("license"), sha256=sha, bytes=pdf.stat().st_size, page_count=n_pages,
            force_ocr=int(force_ocr), status="running", stage="extract", error=None)
        timings: Dict[str, float] = {}

        def stage(name: str, started: float):
            timings[name] = round(time.time() - started, 2)
            totals[name] = totals.get(name, 0.0) + timings[name]
            self.store.update_document(doc_id, stage_timings=json.dumps(timings))

        try:
            ts = time.time()
            pages, image_regions = self.extract(pdf, doc_id, n_pages, force_ocr)
            stage("extract", ts)

            self.store.update_document(doc_id, stage="clean")
            ts = time.time()
            clean = clean_document(pages)
            self.store.save_clean_pages(doc_id, [(cp.text, cp.lang, cp.removed_lines, cp.page_no) for cp in clean])
            lang = document_language(clean)
            stage("clean", ts)

            self.store.update_document(doc_id, stage="chunk")
            ts = time.time()
            chunks = chunk_document(doc_id, clean, self.embedder.count_tokens)
            self.store.replace_chunks(doc_id, [c.to_row() for c in chunks])
            stage("chunk", ts)

            self.store.update_document(doc_id, stage="embed")
            ts = time.time()
            texts = [c.text for c in chunks]
            vecs = []
            for i in tqdm(range(0, len(texts), EMBED_PROGRESS_BATCH), desc=f"embed {pdf.name[:28]}",
                          unit="batch", leave=False, disable=self.quiet):
                vecs.append(self.embedder.embed_passages(texts[i:i + EMBED_PROGRESS_BATCH],
                                                         batch_size=config.EMBED_BATCH_SIZE))
            stage("embed", ts)

            self.store.update_document(doc_id, stage="index")
            ts = time.time()
            import numpy as np
            self.vectors.delete_doc(doc_id)
            if chunks:
                self.vectors.upsert([c.chunk_id for c in chunks], np.concatenate(vecs),
                                    [{"doc_id": doc_id, "chunk_index": c.chunk_index, "page_start": c.page_start,
                                      "page_end": c.page_end} for c in chunks])
            stage("index", ts)

            native = sum(1 for p in pages if p.method != "ocr")
            ocr = n_pages - native
            self.store.update_document(
                doc_id, status="done", stage=None, native_pages=native, ocr_pages=ocr,
                image_ocr_regions=image_regions, chunk_count=len(chunks), language=lang, ingested_at=time.time())
            return DocResult(pdf.name, "done", n_pages, ocr, len(chunks), time.time() - t0,
                             f"lang={lang} img_ocr={image_regions}")
        except KeyboardInterrupt:
            self.store.update_document(doc_id, status="pending", error="interrupted")
            raise
        except Exception as e:  # noqa: BLE001 - one bad PDF must not stop the run
            self.store.update_document(doc_id, status="failed", error=repr(e))
            return DocResult(pdf.name, "failed", n_pages, 0, 0, time.time() - t0, repr(e))

    # ------------------------------------------------------------------ extraction + OCR
    def extract(self, pdf: Path, doc_id: str, n_pages: int, force_ocr: bool):
        cached = {} if self.force else self.store.cached_pages(doc_id)
        pages: Dict[int, PageData] = {pno: _row_to_page(r) for pno, r in cached.items()}
        pending_native: Dict[int, PageData] = {}
        ocr_jobs = []
        image_candidates = []
        to_save: List[dict] = []

        with fitz.open(pdf) as doc:
            for i in tqdm(range(n_pages), desc=f"extract {pdf.name[:28]}", unit="pg", leave=False,
                          disable=self.quiet):
                pno = i + 1
                page = doc[i]
                if pno in pages:
                    # Cached page: still list its image candidates so the capped selection is identical
                    # on every run.
                    if pages[pno].method != "ocr":
                        image_candidates.extend((pno, rect) for rect in large_image_rects(page))
                    continue
                blocks = native_blocks(page)
                pd = PageData(pno, page.rect.width, page.rect.height, "native", blocks)
                if is_native(blocks, force_ocr):
                    pending_native[pno] = pd
                    image_candidates.extend((pno, rect) for rect in large_image_rects(page))
                else:
                    ocr_jobs.append((str(pdf), pno, config.OCR_DPI, None, "page", self.ocr_backend))
                    pages[pno] = PageData(pno, page.rect.width, page.rect.height, "ocr", [])

        # Large-image OCR on native pages: deterministic, evenly spread selection capped per document.
        selected = select_evenly(image_candidates, config.OCR_IMAGES_PER_DOC)
        img_pages = {pno for pno, _ in selected}
        n_regions = len(selected)
        for pno, rect in selected:
            if pno in pending_native:
                ocr_jobs.append((str(pdf), pno, config.OCR_DPI, rect, "image", self.ocr_backend))

        # Native pages without image OCR can be saved right away.
        for pno, pd in list(pending_native.items()):
            if pno not in img_pages:
                pages[pno] = pd
                to_save.append(_page_row(pd))
                del pending_native[pno]
            if len(to_save) >= PAGE_SAVE_BATCH:
                self.store.save_pages(doc_id, to_save)
                to_save = []
        if to_save:
            self.store.save_pages(doc_id, to_save)
            to_save = []

        if ocr_jobs:
            remaining_img = {}
            for job in ocr_jobs:
                if job[4] == "image":
                    remaining_img[job[1]] = remaining_img.get(job[1], 0) + 1
            for r in tqdm(self._ocr_results(ocr_jobs), total=len(ocr_jobs), desc=f"OCR {pdf.name[:30]}",
                          unit="job", leave=False, disable=self.quiet):
                pno = r["page_no"]
                if r["kind"] == "page":
                    pd = pages[pno]
                    pd.blocks = ocr_lines_to_blocks(r["lines"], "ocr")
                    pd.ocr_conf = mean_conf(pd.blocks)
                    pd.error = r["error"]
                    to_save.append(_page_row(pd))
                else:
                    pd = pending_native[pno]
                    native_keys = {_key(ln.text) for b in pd.blocks for ln in b.lines}
                    extra = [l for l in r["lines"] if _key(l[0]) not in native_keys and len(l[0]) > 1]
                    new_blocks = ocr_lines_to_blocks(extra, "image_ocr")
                    if new_blocks:
                        pd.blocks.extend(new_blocks)
                        pd.method = "native+img_ocr"
                        pd.ocr_conf = mean_conf(new_blocks)
                    if r["error"]:
                        pd.error = r["error"]
                    remaining_img[pno] -= 1
                    if remaining_img[pno] == 0:
                        pages[pno] = pd
                        to_save.append(_page_row(pd))
                        del pending_native[pno]
                if len(to_save) >= 10:
                    self.store.save_pages(doc_id, to_save)
                    to_save = []
            if to_save:
                self.store.save_pages(doc_id, to_save)

        for pno, pd in pending_native.items():  # safety net: should be empty
            pages[pno] = pd
            self.store.save_pages(doc_id, [_page_row(pd)])

        return [pages[p] for p in sorted(pages)], n_regions
