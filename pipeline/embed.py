"""
Stage 2: Embedding

Embeds tweets using Qwen3-Embedding-0.6B via sentence-transformers.
Runs on MPS (Apple Silicon). Swap MODEL_NAME for the 4B variant if you
have enough unified memory and want higher quality.

Key design choices:
- Task instruction wraps each tweet for better clustering quality (~1–5% gain)
- Output is L2-normalized → dot product = cosine similarity (FAISS-ready)
- Results cached to disk so re-clustering skips re-embedding
- Embedder class holds the loaded model so it isn't reloaded between calls
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

# Allow MPS to fall back to CPU for kernels it can't handle
# (e.g. SDPA with very long sequences). Must be set before torch is imported.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from pipeline.score import embed_text, score_tweets
from pipeline.types import Tweet

MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
EMBEDDING_DIM = 1024  # 0.6B → 1024-dim; 4B → 2560-dim

# Applied consistently to all tweets (symmetric clustering task).
# Improves cluster separation vs. bare text per Qwen3 embedding docs.
CLUSTER_INSTRUCT = (
    "Instruct: Identify the main topic and subject matter of this tweet "
    "for categorization\nQuery: "
)


class Embedder:
    def __init__(self, model_name: str = MODEL_NAME, device: str = "mps"):
        self.model_name = model_name
        self.device = device
        self.model: SentenceTransformer | None = None

    def load(self) -> "Embedder":
        """Load the model onto the device. Returns self for chaining."""
        print(f"Loading {self.model_name} on {self.device}...")
        t0 = time.time()
        self.model = SentenceTransformer(
            self.model_name,
            device=self.device,
            tokenizer_kwargs={"padding_side": "left"},
        )
        # Cap sequence length — Qwen3-Embedding default can be 8192+, which
        # causes 12GB+ attention buffers on MPS for any long-ish tweet.
        # 512 tokens is more than enough for tweets (typically <150 tokens).
        self.model.max_seq_length = 512
        print(f"  Model loaded in {time.time() - t0:.1f}s")
        return self

    def embed(
        self,
        tweets: list[Tweet],
        cache_path: str | Path | None = None,
    ) -> np.ndarray:
        """
        Embed tweets. Loads the model lazily if not already loaded.

        Args:
            tweets:     Scored tweet dicts (output of score_tweets).
            cache_path: If given, return cached result if it exists;
                        save to disk after encoding.

        Returns:
            np.ndarray shape (N, EMBEDDING_DIM), dtype float32, L2-normalized.
        """
        if cache_path is not None:
            cache_path = Path(cache_path)
            if cache_path.exists():
                print(f"  Cache hit — loading embeddings from {cache_path}")
                return np.load(cache_path)

        if self.model is None:
            self.load()

        texts = [CLUSTER_INSTRUCT + embed_text(t) for t in tweets]
        print(f"  Encoding {len(texts)} tweets (batch_size=16)...")
        t0 = time.time()
        embeddings = self.model.encode(
            texts,
            batch_size=16,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,  # L2-normalize — FAISS-ready
        )
        embeddings = embeddings.astype(np.float32)
        print(f"  Encoded in {time.time() - t0:.1f}s  shape={embeddings.shape}")

        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache_path, embeddings)
            print(f"  Saved to {cache_path}")

        return embeddings


    def embed_query(self, text: str) -> np.ndarray:
        """
        Embed a single query string (no cluster instruction prefix).
        Used by ChatSession to encode user questions for FAISS search.

        Returns:
            np.ndarray shape (EMBEDDING_DIM,), float32, L2-normalized.
        """
        if self.model is None:
            self.load()
        vec = self.model.encode(
            [text],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return vec[0].astype(np.float32)


if __name__ == "__main__":
    input_path = sys.argv[1] if len(sys.argv) > 1 else "timeline_20260313_194631.json"

    with open(input_path) as f:
        raw_tweets = json.load(f)

    tweets = score_tweets(raw_tweets)
    print(f"Tweets after scoring/filtering: {len(tweets)}")

    cache_path = Path("cache") / (Path(input_path).stem + "_embeddings.npy")
    embeddings = Embedder().embed(tweets, cache_path=cache_path)

    print(f"\nEmbedding shape: {embeddings.shape}")
    print(f"Sample norm (should be ~1.0): {np.linalg.norm(embeddings[0]):.6f}")

    # Sanity check: find top similar tweet pairs via pairwise dot product
    print("\nTop 10 most similar tweet pairs (cosine similarity):")
    sample = embeddings[:200]
    sims = sample @ sample.T
    np.fill_diagonal(sims, -1)

    pairs = []
    for i in range(len(sample)):
        j = int(np.argmax(sims[i]))
        pairs.append((float(sims[i, j]), i, j))
    pairs.sort(reverse=True)

    seen: set[tuple[int, int]] = set()
    shown = 0
    for score, i, j in pairs:
        key = (min(i, j), max(i, j))
        if key in seen:
            continue
        seen.add(key)
        print(f"\n  sim={score:.4f}")
        print(f"  [{i}] @{tweets[i]['user']['screen_name']}: {tweets[i]['text'][:90].replace(chr(10), ' ')}")
        print(f"  [{j}] @{tweets[j]['user']['screen_name']}: {tweets[j]['text'][:90].replace(chr(10), ' ')}")
        shown += 1
        if shown >= 10:
            break
