"""Shared paths and model/chunking settings for ingestion and the API.

Values come from environment variables (loaded from the repo-root .env) with
defaults tuned for a 2-core / 4-thread laptop CPU.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


DATA_DIR = Path(_env("GRANTH_DATA_DIR", str(ROOT_DIR / "data")))
PDF_DIR = DATA_DIR / "pdfs"
CHROMA_DIR = DATA_DIR / "chroma"
SQLITE_PATH = DATA_DIR / "granth.db"
MODEL_CACHE_DIR = DATA_DIR / "models"
CORPUS_FILE = ROOT_DIR / "corpus.yaml"

CHROMA_COLLECTION = "granth_chunks"

EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = 384
EMBED_BATCH_SIZE = int(_env("EMBED_BATCH_SIZE", "32"))

# Chunking (tokens measured with the embedding model's tokenizer).
CHUNK_TARGET_TOKENS = int(_env("CHUNK_TARGET_TOKENS", "480"))
CHUNK_MAX_TOKENS = int(_env("CHUNK_MAX_TOKENS", "510"))
CHUNK_OVERLAP_TOKENS = int(_env("CHUNK_OVERLAP_TOKENS", "72"))

# Extraction / OCR.
NATIVE_MIN_CHARS = int(_env("NATIVE_MIN_CHARS", "80"))
OCR_DPI = int(_env("OCR_DPI", "200"))
OCR_IMAGE_MIN_AREA_FRAC = float(_env("OCR_IMAGE_MIN_AREA_FRAC", "0.25"))
OCR_IMAGES_PER_DOC = int(_env("OCR_IMAGES_PER_DOC", "0"))
OCR_WORKERS = max(1, min(3, int(_env("OCR_WORKERS", str(max(1, (os.cpu_count() or 2) - 1))))))
OCR_BACKEND = _env("OCR_BACKEND", "auto")  # auto | rapidocr | tesseract

# Header/footer detection.
HF_BAND_FRAC = 0.08
HF_MIN_PAGE_FRAC = 0.06
HF_MIN_PAGES = 3
HF_WINDOW = 50


def ensure_dirs() -> None:
    for d in (DATA_DIR, PDF_DIR, CHROMA_DIR, MODEL_CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
