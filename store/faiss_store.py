"""
FAISS vector store for the tweet digest pipeline.

Builds a flat inner-product index over L2-normalized tweet embeddings
(dot product on normalized vecs = cosine similarity). Saves the index
and a companion metadata JSON so query results can be resolved to tweets.
"""

from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np

from pipeline.types import Tweet

STORE_DIR = Path("out")


class FAISSStore:
    def __init__(self) -> None:
        self.index: faiss.IndexFlatIP | None = None
        self.meta: list[dict] = []  # parallel to index vectors

    # ── build / persist ───────────────────────────────────────────────────────

    def build(self, tweets: list[Tweet], embeddings: np.ndarray, date: str) -> None:
        """
        Build an IndexFlatIP from L2-normalized embeddings and save to disk.

        Args:
            tweets:     Tweets in the same order as embeddings rows.
            embeddings: np.ndarray shape (N, dim), float32, L2-normalized.
            date:       ISO date string used as the filename key.
        """
        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(embeddings.astype(np.float32))

        self.meta = [
            {
                "id": t["id"],
                "text": t.get("text", ""),
                "url": t.get("url", f"https://twitter.com/i/web/status/{t['id']}"),
                "importance_score": t.get("importance_score", 0.0),
            }
            for t in tweets
        ]

        STORE_DIR.mkdir(parents=True, exist_ok=True)
        index_path = STORE_DIR / f"{date}.faiss"
        meta_path = STORE_DIR / f"{date}_meta.json"

        faiss.write_index(self.index, str(index_path))
        meta_path.write_text(json.dumps(self.meta, ensure_ascii=False, indent=2))

        print(f"  FAISS index ({self.index.ntotal} vectors, dim={dim}) → {index_path}")
        print(f"  Metadata → {meta_path}")

    @classmethod
    def load(cls, date: str, store_dir: str | Path = STORE_DIR) -> "FAISSStore":
        """Load a previously built index from disk."""
        store_dir = Path(store_dir)
        index_path = store_dir / f"{date}.faiss"
        meta_path = store_dir / f"{date}_meta.json"

        if not index_path.exists():
            raise FileNotFoundError(f"No FAISS index found at {index_path}")

        obj = cls()
        obj.index = faiss.read_index(str(index_path))
        obj.meta = json.loads(meta_path.read_text())
        return obj

    @classmethod
    def latest(cls, store_dir: str | Path = STORE_DIR) -> "FAISSStore":
        """Load the most recently built index."""
        store_dir = Path(store_dir)
        faiss_files = sorted(store_dir.glob("*.faiss"))
        if not faiss_files:
            raise FileNotFoundError(f"No .faiss files found in {store_dir}")
        date = faiss_files[-1].stem
        print(f"  Loading FAISS index for {date}")
        return cls.load(date, store_dir)

    # ── query ─────────────────────────────────────────────────────────────────

    def query(self, embedding: np.ndarray, k: int = 20) -> list[dict]:
        """
        Find the k nearest tweets to the given embedding.

        Args:
            embedding: shape (dim,) or (1, dim), float32, L2-normalized.
            k:         Number of results to return.

        Returns:
            List of tweet metadata dicts (id, text, url, importance_score).
        """
        if self.index is None:
            raise RuntimeError("Index not loaded — call build() or load() first.")

        q = embedding.reshape(1, -1).astype(np.float32)
        k = min(k, self.index.ntotal)
        _distances, indices = self.index.search(q, k)

        return [self.meta[i] for i in indices[0] if i >= 0]
