"""Benchmarks the local models on this CPU (embedding throughput, query embedding, reranker latency).

    python scripts/bench_models.py
"""
import os
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

PASSAGE = ("The cell membrane regulates the transport of molecules into and out of the cell, using channel and "
           "carrier proteins as well as active pumps powered by ATP. ") * 14
QUERY = "How do carrier proteins move molecules across the membrane?"


def timed(fn, repeat=3):
    fn()
    samples = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t)
    return statistics.median(samples)


def main():
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    from ingestion.config import MODEL_CACHE_DIR
    from ingestion.embedder import Embedder

    print(f"CPU: {platform.processor()} · {os.cpu_count()} logical cores · Python {platform.python_version()}")
    emb = Embedder()
    n_tok = emb.count_tokens([PASSAGE])[0]
    batch = [PASSAGE] * 32
    dt = timed(lambda: emb.embed_passages(batch), repeat=1)
    print(f"embed passages ({n_tok} tokens): {32 / dt:.2f} passages/s")
    dt = timed(lambda: emb.embed_query(QUERY), repeat=10)
    print(f"embed query: {dt * 1000:.1f} ms")

    for name in ["Xenova/ms-marco-MiniLM-L-6-v2", "jinaai/jina-reranker-v1-tiny-en", "Xenova/ms-marco-MiniLM-L-12-v2"]:
        ce = TextCrossEncoder(name, cache_dir=str(MODEL_CACHE_DIR), threads=os.cpu_count())
        for max_len in (512, 256):
            ce.model.tokenizer.enable_truncation(max_length=max_len)
            for n in (20, 12):
                docs = [PASSAGE] * n
                dt = timed(lambda: list(ce.rerank(QUERY, docs, batch_size=n)))
                print(f"rerank {name:<34} max_len={max_len} n={n}: {dt * 1000:.0f} ms")


if __name__ == "__main__":
    main()
