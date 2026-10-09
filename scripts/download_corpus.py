"""Download and verify the Granth demo corpus described in corpus.yaml.

    python scripts/download_corpus.py               # fetch everything (resumes partial downloads)
    python scripts/download_corpus.py --synthetic   # also build the image-only synthetic scan
    python scripts/download_corpus.py --only biology-2e

Writes data/pdfs/<filename>, data/pdfs/manifest.json (read by the ingestion pipeline) and
data/ATTRIBUTION.md. Each file's page count is verified with PyMuPDF; an entry that fails
moves on to its alternates.
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import pymupdf as fitz  # PyMuPDF
import requests
import yaml
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingestion.config import CORPUS_FILE, DATA_DIR, PDF_DIR, ensure_dirs  # noqa: E402

HEADERS = {"User-Agent": "granth-corpus/1.0 (+open-source PDF RAG demo)"}
OPENSTAX_API = "https://openstax.org/apps/cms/api/v2/pages/"
MANIFEST = PDF_DIR / "manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, dest: Path, retries: int = 3) -> None:
    """Streams `url` to `dest`, resuming a previous partial download (.part) with HTTP Range."""
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            have = part.stat().st_size if part.exists() else 0
            headers = dict(HEADERS)
            if have:
                headers["Range"] = f"bytes={have}-"
            with requests.get(url, headers=headers, stream=True, timeout=(20, 120), allow_redirects=True) as r:
                if r.status_code == 416:  # already complete
                    part.replace(dest)
                    return
                r.raise_for_status()
                if have and r.status_code != 206:  # server ignored Range: start over
                    have = 0
                total = int(r.headers.get("Content-Length", 0)) + have
                mode = "ab" if have else "wb"
                with open(part, mode) as f, tqdm(total=total or None, initial=have, unit="B", unit_scale=True,
                                                 desc=dest.name[:40], leave=False) as bar:
                    for block in r.iter_content(chunk_size=1 << 16):
                        f.write(block)
                        bar.update(len(block))
            part.replace(dest)
            return
        except (requests.RequestException, OSError) as e:
            print(f"    attempt {attempt}/{retries} failed: {e}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"download failed: {url}")


def page_count(path: Path) -> int:
    with fitz.open(path) as doc:
        return doc.page_count


def openstax_lookup() -> dict:
    try:
        r = requests.get(OPENSTAX_API, headers=HEADERS, timeout=60, params={
            "type": "books.Book", "fields": "title,high_resolution_pdf_url,license_name,license_url",
            "limit": 250})
        r.raise_for_status()
        return {it["title"]: it for it in r.json()["items"]}
    except Exception as e:  # noqa: BLE001
        print(f"  OpenStax API unavailable ({e}); falling back to URLs in corpus.yaml")
        return {}


def archive_pdf_url(identifier: str) -> tuple:
    m = requests.get(f"https://archive.org/metadata/{identifier}", headers=HEADERS, timeout=60).json()
    pdfs = [f for f in m.get("files", []) if f["name"].lower().endswith(".pdf")]
    if not pdfs:
        raise RuntimeError(f"no PDF in archive.org item {identifier}")
    # Prefer the colour/greyscale scan PDF over the bilevel _bw variant.
    pdfs.sort(key=lambda f: ("_bw" in f["name"], f["name"]))
    md = m.get("metadata", {})
    return f"https://archive.org/download/{identifier}/{pdfs[0]['name']}", md


def fetch_entry(entry: dict, min_pages: int, osx: dict) -> dict:
    dest = PDF_DIR / entry["filename"]
    candidates = []  # (url, extra metadata)
    if entry["source"] == "openstax":
        api = osx.get(entry.get("openstax_title", entry["title"]))
        if api and api.get("high_resolution_pdf_url"):
            candidates.append((api["high_resolution_pdf_url"], {
                "license": api.get("license_name"), "license_url": api.get("license_url")}))
        for u in entry.get("urls", []):
            candidates.append((u, {}))
    elif entry["source"] == "archive.org":
        for ident in [entry["identifier"], *entry.get("alternates", [])]:
            try:
                url, md = archive_pdf_url(ident)
                candidates.append((url, {"identifier": ident, "archive_title": md.get("title"),
                                         "archive_date": md.get("date"), "details_url": f"https://archive.org/details/{ident}"}))
            except Exception as e:  # noqa: BLE001
                print(f"    archive.org lookup failed for {ident}: {e}")
    else:
        candidates.extend((u, {}) for u in entry.get("urls", []))

    seen = set()
    for url, extra in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            if not dest.exists():
                download(url, dest)
            n = page_count(dest)
            if n < min_pages:
                raise RuntimeError(f"only {n} pages (< {min_pages})")
            info = {k: v for k, v in entry.items() if k not in ("urls", "alternates", "openstax_title")}
            info.update({k: v for k, v in extra.items() if v})
            if extra.get("archive_title") and extra.get("identifier") != entry.get("identifier"):
                info["title"] = f"{extra['archive_title']} ({extra.get('archive_date', '')})".strip()
            info.update({"source_url": url, "pages": n, "sha256": sha256_file(dest),
                         "bytes": dest.stat().st_size})
            return info
        except Exception as e:  # noqa: BLE001
            print(f"    {entry['id']}: candidate failed ({url}): {e}")
            if dest.exists():
                dest.unlink()
    raise RuntimeError(f"{entry['id']}: every candidate failed")


def build_synthetic(spec: dict, manifest: dict) -> dict:
    src_entry = manifest.get(spec["from"])
    if not src_entry:
        raise RuntimeError(f"synthetic scan needs '{spec['from']}' to be downloaded first")
    src = PDF_DIR / src_entry["filename"]
    dest = PDF_DIR / spec["filename"]
    first = spec["first_page"] - 1
    count = spec["page_count"]
    if not dest.exists():
        out = fitz.open()
        with fitz.open(src) as doc:
            for i in tqdm(range(first, min(first + count, doc.page_count)), desc="rasterising", leave=False):
                page = doc[i]
                pix = page.get_pixmap(dpi=spec["dpi"], colorspace=fitz.csGRAY)
                p = out.new_page(width=page.rect.width, height=page.rect.height)
                p.insert_image(p.rect, stream=pix.tobytes("jpeg", jpg_quality=80))
        out.save(dest, garbage=4, deflate=True)
        out.close()
    n = page_count(dest)
    with fitz.open(dest) as d:
        text_chars = sum(len(d[i].get_text().strip()) for i in range(min(5, n)))
    assert text_chars == 0, "synthetic scan unexpectedly contains a text layer"
    return {"id": spec["id"], "filename": spec["filename"], "title": spec["title"],
            "authors": src_entry.get("authors"), "source": "synthetic",
            "license": src_entry.get("license"), "license_url": src_entry.get("license_url"),
            "derived_from": src_entry["filename"], "source_url": src_entry.get("source_url"),
            "force_ocr": True, "pages": n, "sha256": sha256_file(dest), "bytes": dest.stat().st_size}


def write_attribution(manifest: dict) -> None:
    lines = [
        "# Corpus attribution", "",
        f"Generated by `scripts/download_corpus.py` on {dt.date.today().isoformat()}. "
        "Files are stored locally in `data/pdfs/` and are not redistributed with this repository.", "",
        "| File | Title | Authors | Pages | License | Source |", "|---|---|---|---|---|---|",
    ]
    for e in manifest.values():
        lic = e.get("license") or ""
        if e.get("license_url"):
            lic = f"[{lic}]({e['license_url']})"
        src = e.get("details_url") or e.get("source_url", "")
        lines.append(f"| `{e['filename']}` | {e['title']} | {e.get('authors', '')} | {e['pages']} | {lic} | {src} |")
    lines += ["", "OpenStax textbooks © Rice University, used under the license shown (the license name is read "
              "from the OpenStax CMS API at download time). Changes: none to the files; Granth extracts, chunks "
              "and indexes the text for retrieval.",
              "", "archive.org scans are public-domain works (published before 1929). Granth re-OCRs them.",
              "", "Synthetic scans (if present) are image-only re-renderings of the named OpenStax book, made to "
              "exercise the OCR path; they carry the same license as the source book."]
    (DATA_DIR / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="ids to fetch")
    ap.add_argument("--synthetic", action="store_true", help="always build the synthetic image-only scan")
    args = ap.parse_args()

    ensure_dirs()
    cfg = yaml.safe_load(CORPUS_FILE.read_text(encoding="utf-8"))
    min_pages = cfg.get("min_pages", 200)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    osx = openstax_lookup() if any(d["source"] == "openstax" for d in cfg["documents"]) else {}

    failed = []
    for entry in cfg["documents"]:
        if args.only and entry["id"] not in args.only:
            continue
        print(f"- {entry['id']}")
        try:
            manifest[entry["id"]] = fetch_entry(entry, min_pages, osx)
            e = manifest[entry["id"]]
            print(f"    ok: {e['filename']} · {e['pages']} pages · {e['bytes'] / 1e6:.1f} MB")
        except Exception as e:  # noqa: BLE001
            print(f"    FAILED: {e}")
            failed.append(entry["id"])
            manifest.pop(entry["id"], None)
        MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    scanned = [e for e in manifest.values() if e.get("force_ocr")]
    syn = cfg.get("synthetic")
    if syn and (args.synthetic or not scanned):
        print(f"- {syn['id']} (synthetic image-only scan)")
        manifest[syn["id"]] = build_synthetic(syn, manifest)
        MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    write_attribution(manifest)
    print("\n{:<48} {:>6} {:>9}  {}".format("file", "pages", "MB", "license"))
    for e in manifest.values():
        print("{:<48} {:>6} {:>9.1f}  {}".format(e["filename"], e["pages"], e["bytes"] / 1e6, (e.get("license") or "")[:50]))
    short = [e["filename"] for e in manifest.values() if e["pages"] < min_pages]
    print(f"\n{len(manifest)} PDFs, {sum(e['pages'] for e in manifest.values())} pages total; "
          f"{len(scanned)} scanned; failures: {failed or 'none'}; under {min_pages} pages: {short or 'none'}")
    return 1 if failed or short else 0


if __name__ == "__main__":
    sys.exit(main())
