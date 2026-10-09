"""ChromaDB persistent HNSW index (cosine). Vectors live in data/chroma; chunk text stays in SQLite."""
import os
from typing import Dict, List, Optional

import numpy as np

from ingestion.config import CHROMA_COLLECTION, CHROMA_DIR

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

UPSERT_BATCH = 256


class VectorStore:
    def __init__(self, path=CHROMA_DIR):
        import chromadb
        from chromadb.config import Settings
        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.get_or_create_collection(
            CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine", "hnsw:construction_ef": 200, "hnsw:M": 16, "hnsw:search_ef": 96},
        )

    def count(self) -> int:
        return self.collection.count()

    def delete_doc(self, doc_id: str) -> None:
        self.collection.delete(where={"doc_id": doc_id})

    def count_doc(self, doc_id: str) -> int:
        return len(self.collection.get(where={"doc_id": doc_id}, include=[])["ids"])

    def upsert(self, ids: List[str], embeddings: np.ndarray, metadatas: List[Dict]) -> None:
        for i in range(0, len(ids), UPSERT_BATCH):
            self.collection.upsert(ids=ids[i:i + UPSERT_BATCH],
                                   embeddings=embeddings[i:i + UPSERT_BATCH].tolist(),
                                   metadatas=metadatas[i:i + UPSERT_BATCH])

    def query(self, embedding: List[float], top_k: int = 30, doc_ids: Optional[List[str]] = None) -> List[tuple]:
        """Returns [(chunk_id, cosine_similarity)] best first."""
        where = None
        if doc_ids:
            where = {"doc_id": doc_ids[0]} if len(doc_ids) == 1 else {"doc_id": {"$in": doc_ids}}
        res = self.collection.query(query_embeddings=[embedding], n_results=top_k, where=where, include=["distances"])
        ids = res["ids"][0] if res["ids"] else []
        dists = res["distances"][0] if res.get("distances") else []
        return [(cid, 1.0 - float(d)) for cid, d in zip(ids, dists)]
