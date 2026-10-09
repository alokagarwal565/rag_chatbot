# Granth — working notes

Open-source, fully local PDF RAG assistant (hackathon "Challenge 1: RAG Chatbot").
Target machine: Windows 11, Intel i3-8130U (2C/4T), 12 GB RAM, no GPU.

## Run commands (PowerShell, from the repo root)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
cd frontend; npm install; cd ..

.venv\Scripts\python scripts\download_corpus.py         # PDFs -> data\pdfs, data\ATTRIBUTION.md
.venv\Scripts\python -m ingestion                        # PDF -> chunks -> embeddings -> Chroma + SQLite
.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 7860
cd frontend; npm run dev                                 # http://localhost:5173 (proxies /api -> 7860)

.venv\Scripts\python -m pytest backend\tests -q          # or: cd backend; ..\.venv\Scripts\python -m pytest
.venv\Scripts\python scripts\check_branding.py           # must report 0 hits
.venv\Scripts\python -m evaluation.runner                # writes evaluation\report.md / report.json
```

## Fixed decisions

| Area | Decision |
|---|---|
| Vector DB | ChromaDB PersistentClient (HNSW, cosine) in `data/chroma` |
| Metadata + lexical | SQLite `data/granth.db` with FTS5 (BM25) |
| Retrieval | Chroma dense top-30 + FTS5 top-30 → RRF (k=60) → rerank → top-6 to LLM |
| Embeddings | `BAAI/bge-small-en-v1.5` (384-d) via fastembed ONNX; `query_embed` for queries |
| Reranker | ONNX MiniLM cross-encoder via fastembed, toggle `RERANKER_ENABLED` |
| OCR | `rapidocr-onnxruntime`; Tesseract only if on PATH |
| Chunking | ~480 tokens (cap 510, bge window is 512) with 72 overlap (15%), embedder tokenizer |
| LLM | Gemini via `google-genai`, keys rotate on 429, per-tier model fallback, SSE streaming, output cap |
| Language | `langdetect`, seeded |
| Data | everything under `./data/` (gitignored) |

## Layout
- `ingestion/` — pipeline + shared storage code (`store.py` SQLite, `vector_store.py` Chroma, `embedder.py`).
  The backend imports it, so run uvicorn from the repo root with `--app-dir backend`.
- `backend/app/` — FastAPI app (`/api/v1/query` SSE, documents, ingestion status, evaluation report).
- `frontend/` — React 18 + Vite + TS; tabs Chat / Ingestion / Metrics.
- `evaluation/` — eval set builder, runner, judge, report.
- `scripts/` — corpus download, branding check, model benchmark.

## Git rules
- Never push from the agent; never commit `.env`, PDFs or `data/`.
- Run `scripts/check_branding.py` before committing.

## Gotchas
- Only Python 3.14 was preinstalled; 3.12 was installed via winget and is used through `.venv`.
- `check_branding.py` stores banned terms as salted hashes. Lockfile `integrity`/`license` lines are skipped
  (base64 noise and BSD license names).
- npm 11 prints an `allow-scripts` warning for esbuild's postinstall; the build still works because the
  platform binary comes from an optional dependency.
- The injection regex is intentionally narrow: "how do enzymes act as catalysts" must reach RAG.
- Gemini `3.5-flash-lite` rejects `thinking_budget=0` with a bare 400; the provider drops the thinking config for
  that model and retries the same key. Other 4xx errors skip the model's remaining keys.
- OCR workers can be killed under memory pressure (12 GB box, 3 workers + API + models). The pipeline restarts the
  pool, then isolates a crashing job. Don't run the API and a large ingestion at the same time.
- Benchmarks on the i3: embedding ~3 passages/s at 450 tokens (≈80-90 min for the corpus), RapidOCR ~4-9 s/page,
  reranker MiniLM-L6 12×256 tokens ≈0.76 s.
- Don't pass regex replacement strings with backslashes through shell heredocs: they reached a .py file as
  control characters. Use the Edit/Write tools.
- Fast-track settings: OCR_IMAGES_PER_DOC=0; the 1901 plant-life scan is ingested via its archive.org text layer,
  so the 1920 relativity scan is the one fully OCR'd document.
