"""fastembed (ONNX Runtime, CPU) wrapper for bge-small-en-v1.5, shared by ingestion and the API.

Measured on an i3-8130U: ~3.6 passages/s at ~450 tokens (compute-bound; int8 vs fp32 and thread
counts change this by <10%), ~15 ms per query embedding.
"""
import os
import threading
from typing import Iterable, List, Optional

import numpy as np

from ingestion.config import EMBEDDING_MODEL, MODEL_CACHE_DIR

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

_LOCK = threading.Lock()
_INSTANCE: Optional["Embedder"] = None


class Embedder:
    def __init__(self, model_name: str = EMBEDDING_MODEL, threads: Optional[int] = None):
        from fastembed import TextEmbedding
        MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self.model = TextEmbedding(model_name, cache_dir=str(MODEL_CACHE_DIR),
                                   threads=threads or os.cpu_count() or 4)
        # A separate, non-truncating copy of the model's own tokenizer, used for chunk sizing.
        from tokenizers import Tokenizer
        self.tokenizer: Tokenizer = Tokenizer.from_str(self.model.model.tokenizer.to_str())
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()

    def count_tokens(self, texts: List[str]) -> List[int]:
        """Token counts without special tokens ([CLS]/[SEP] add 2 more at embed time)."""
        return [len(e.ids) for e in self.tokenizer.encode_batch(texts, add_special_tokens=False)]

    def embed_passages(self, texts: Iterable[str], batch_size: int = 32) -> np.ndarray:
        return np.asarray(list(self.model.passage_embed(list(texts), batch_size=batch_size)), dtype=np.float32)

    def embed_query(self, text: str) -> List[float]:
        return next(iter(self.model.query_embed(text))).astype(np.float32).tolist()


def get_embedder() -> Embedder:
    """Process-wide singleton (model load takes a few seconds)."""
    global _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            _INSTANCE = Embedder()
        return _INSTANCE
