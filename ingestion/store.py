"""SQLite metadata store (stdlib sqlite3) with an FTS5 index for BM25.

Tables: documents, pages (per-page extraction + OCR cache), chunks, chunks_fts (external-content
FTS5 kept in sync by triggers), ingestion_runs (per-stage timings).
"""
import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ingestion.config import SQLITE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id        TEXT PRIMARY KEY,
    filename      TEXT NOT NULL UNIQUE,
    title         TEXT,
    authors       TEXT,
    source        TEXT,
    source_url    TEXT,
    license       TEXT,
    sha256        TEXT NOT NULL,
    bytes         INTEGER,
    page_count    INTEGER,
    native_pages  INTEGER DEFAULT 0,
    ocr_pages     INTEGER DEFAULT 0,
    image_ocr_regions INTEGER DEFAULT 0,
    chunk_count   INTEGER DEFAULT 0,
    language      TEXT,
    force_ocr     INTEGER DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'pending',   -- pending | running | done | failed
    stage         TEXT,
    error         TEXT,
    stage_timings TEXT DEFAULT '{}',
    created_at    REAL,
    updated_at    REAL,
    ingested_at   REAL
);

CREATE TABLE IF NOT EXISTS pages (
    doc_id      TEXT NOT NULL,
    page_no     INTEGER NOT NULL,
    width       REAL,
    height      REAL,
    method      TEXT,          -- native | ocr | native+img_ocr
    char_count  INTEGER,
    ocr_conf    REAL,
    lang        TEXT,
    blocks_json TEXT,          -- raw extracted blocks (native and/or OCR), the OCR cache
    clean_text  TEXT,
    removed_lines INTEGER,
    error       TEXT,
    PRIMARY KEY (doc_id, page_no)
);

CREATE TABLE IF NOT EXISTS chunks (
    rowid       INTEGER PRIMARY KEY,
    chunk_id    TEXT NOT NULL UNIQUE,
    doc_id      TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page_start  INTEGER NOT NULL,
    page_end    INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    bboxes_json TEXT NOT NULL,
    lang        TEXT,
    has_ocr     INTEGER DEFAULT 0,
    text        TEXT NOT NULL,
    UNIQUE (doc_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='rowid', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    REAL,
    finished_at   REAL,
    status        TEXT,
    docs_total    INTEGER,
    docs_done     INTEGER DEFAULT 0,
    stage_timings TEXT DEFAULT '{}',
    error         TEXT
);
"""

_FTS_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
FTS_STOPWORDS = frozenset("""a an and are as at be by can could did do does for from had has have how i if in into is
it its of on or so such than that the their them then there these they this to was we were what when where which
who whom why will with would you your about between does explain describe""".split())


def fts_query(text: str, max_terms: int = 24) -> Optional[str]:
    """Turns free text into a safe FTS5 query: quoted terms OR'ed together (stopwords dropped)."""
    terms, seen = [], set()
    for t in _FTS_TOKEN_RE.findall(text.lower()):
        if (len(t) < 2 and not t.isdigit()) or t in FTS_STOPWORDS or t in seen:
            continue
        seen.add(t)
        terms.append(f'"{t}"')
        if len(terms) >= max_terms:
            break
    return " OR ".join(terms) if terms else None


class Store:
    def __init__(self, path: Path = SQLITE_PATH, read_only: bool = False):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._local = threading.local()
        self.read_only = read_only
        if not read_only:
            with self.conn:
                self.conn.executescript(SCHEMA)

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA foreign_keys=ON")
            self._local.conn = c
        return c

    # ---------------- documents ----------------
    def get_document(self, doc_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()

    def get_document_by_filename(self, filename: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM documents WHERE filename=?", (filename,)).fetchone()

    def list_documents(self) -> List[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM documents ORDER BY filename").fetchall()

    def upsert_document(self, **fields) -> None:
        now = time.time()
        fields.setdefault("updated_at", now)
        existing = self.get_document(fields["doc_id"])
        with self.conn:
            if existing is None:
                fields.setdefault("created_at", now)
                cols = ", ".join(fields)
                qs = ", ".join("?" for _ in fields)
                self.conn.execute(f"INSERT INTO documents ({cols}) VALUES ({qs})", list(fields.values()))
            else:
                sets = ", ".join(f"{k}=?" for k in fields if k != "doc_id")
                vals = [v for k, v in fields.items() if k != "doc_id"]
                self.conn.execute(f"UPDATE documents SET {sets} WHERE doc_id=?", [*vals, fields["doc_id"]])

    def update_document(self, doc_id: str, **fields) -> None:
        fields["updated_at"] = time.time()
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.conn:
            self.conn.execute(f"UPDATE documents SET {sets} WHERE doc_id=?", [*fields.values(), doc_id])

    def delete_document(self, doc_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
            self.conn.execute("DELETE FROM pages WHERE doc_id=?", (doc_id,))
            self.conn.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))

    # ---------------- pages ----------------
    def cached_pages(self, doc_id: str) -> Dict[int, sqlite3.Row]:
        rows = self.conn.execute("SELECT * FROM pages WHERE doc_id=? AND blocks_json IS NOT NULL", (doc_id,))
        return {r["page_no"]: r for r in rows}

    def save_pages(self, doc_id: str, pages: Iterable[dict]) -> None:
        with self.conn:
            self.conn.executemany(
                """INSERT INTO pages (doc_id, page_no, width, height, method, char_count, ocr_conf, blocks_json, error)
                   VALUES (:doc_id, :page_no, :width, :height, :method, :char_count, :ocr_conf, :blocks_json, :error)
                   ON CONFLICT(doc_id, page_no) DO UPDATE SET width=excluded.width, height=excluded.height,
                     method=excluded.method, char_count=excluded.char_count, ocr_conf=excluded.ocr_conf,
                     blocks_json=excluded.blocks_json, error=excluded.error""",
                [{**p, "doc_id": doc_id} for p in pages])

    def save_clean_pages(self, doc_id: str, rows: Iterable[tuple]) -> None:
        """rows: (clean_text, lang, removed_lines, page_no)"""
        with self.conn:
            self.conn.executemany(
                "UPDATE pages SET clean_text=?, lang=?, removed_lines=? WHERE doc_id=? AND page_no=?",
                [(t, lang, rem, doc_id, pno) for t, lang, rem, pno in rows])

    def page_info(self, doc_id: str, page_no: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT doc_id, page_no, width, height, method, ocr_conf, lang FROM pages "
                                 "WHERE doc_id=? AND page_no=?", (doc_id, page_no)).fetchone()

    # ---------------- chunks ----------------
    def replace_chunks(self, doc_id: str, chunks: List[dict]) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
            self.conn.executemany(
                """INSERT INTO chunks (chunk_id, doc_id, chunk_index, page_start, page_end, token_count,
                                       bboxes_json, lang, has_ocr, text)
                   VALUES (:chunk_id, :doc_id, :chunk_index, :page_start, :page_end, :token_count,
                           :bboxes_json, :lang, :has_ocr, :text)""", chunks)

    def chunk_ids_for_doc(self, doc_id: str) -> List[str]:
        return [r[0] for r in self.conn.execute(
            "SELECT chunk_id FROM chunks WHERE doc_id=? ORDER BY chunk_index", (doc_id,))]

    def chunks_for_doc(self, doc_id: str) -> List[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM chunks WHERE doc_id=? ORDER BY chunk_index", (doc_id,)).fetchall()

    def get_chunks(self, chunk_ids: List[str]) -> Dict[str, sqlite3.Row]:
        if not chunk_ids:
            return {}
        out = {}
        for i in range(0, len(chunk_ids), 500):
            part = chunk_ids[i:i + 500]
            qs = ",".join("?" for _ in part)
            for r in self.conn.execute(
                    f"""SELECT c.*, d.filename, d.title FROM chunks c JOIN documents d USING (doc_id)
                        WHERE c.chunk_id IN ({qs})""", part):
                out[r["chunk_id"]] = r
        return out

    def bm25_search(self, query: str, top_k: int = 30, doc_ids: Optional[List[str]] = None) -> List[tuple]:
        """Returns [(chunk_id, score)] with score = -bm25 (higher is better)."""
        q = fts_query(query)
        if not q:
            return []
        sql = """SELECT c.chunk_id, -bm25(chunks_fts) AS score
                 FROM chunks_fts JOIN chunks c ON c.rowid = chunks_fts.rowid
                 WHERE chunks_fts MATCH ?"""
        params: list = [q]
        if doc_ids:
            sql += f" AND c.doc_id IN ({','.join('?' for _ in doc_ids)})"
            params += doc_ids
        sql += " ORDER BY bm25(chunks_fts) LIMIT ?"
        params.append(top_k)
        return [(r[0], float(r[1])) for r in self.conn.execute(sql, params)]

    # ---------------- runs / stats ----------------
    def start_run(self, docs_total: int) -> int:
        with self.conn:
            cur = self.conn.execute("INSERT INTO ingestion_runs (started_at, status, docs_total) VALUES (?, 'running', ?)",
                                    (time.time(), docs_total))
            return cur.lastrowid

    def finish_run(self, run_id: int, status: str, docs_done: int, stage_timings: dict, error: str = None) -> None:
        with self.conn:
            self.conn.execute("UPDATE ingestion_runs SET finished_at=?, status=?, docs_done=?, stage_timings=?, error=? "
                              "WHERE run_id=?", (time.time(), status, docs_done, json.dumps(stage_timings), error, run_id))

    def last_run(self) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM ingestion_runs ORDER BY run_id DESC LIMIT 1").fetchone()

    def totals(self) -> dict:
        r = self.conn.execute("""SELECT COUNT(*) AS documents, COALESCE(SUM(page_count),0) AS pages,
                                        COALESCE(SUM(native_pages),0) AS native_pages, COALESCE(SUM(ocr_pages),0) AS ocr_pages,
                                        COALESCE(SUM(chunk_count),0) AS chunks
                                 FROM documents WHERE status='done'""").fetchone()
        return dict(r)
