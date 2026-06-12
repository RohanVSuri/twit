"""
Stage 3: Clustering

Reduces high-dimensional embeddings with UMAP, then clusters with HDBSCAN.
Deduplicates near-identical tweets within each cluster.

Pipeline:
    embeddings (N, 1024)
      → UMAP  → (N, 15)         fixes curse of dimensionality
      → HDBSCAN sweep            tries ~15 min_cluster_size values with EOM;
                                  picks the best result for [target_min, target_max]
      → size-aware merge         collapses excess clusters without creating a
                                  "black hole" cluster that absorbs everything
      → dedup                    drops cosine sim > 0.95 within each cluster
      → list[Cluster]

Tuning:
  - target_min / target_max: desired cluster count range (default 5–20)
  - The sweep tries candidate values automatically; no manual tuning needed
"""

import json
import sys
from pathlib import Path

import hdbscan
import numpy as np
import threading
import umap

# Numba's default workqueue threading layer is not thread-safe.
# Jobs run in background threads (see runner.py), so we serialize UMAP
# calls with a process-wide lock to prevent the workqueue crash.
_umap_lock = threading.Lock()

from pipeline.types import Cluster, Tweet


class Clusterer:
    def __init__(
        self,
        target_min: int = 9,
        target_max: int = 14,
        umap_components: int = 5,
        dedup_threshold: float = 0.95,
        random_state: int = 42,
    ):
        self.target_min = target_min
        self.target_max = target_max
        self.umap_components = umap_components
        self.dedup_threshold = dedup_threshold
        self.random_state = random_state

    def cluster(self, tweets: list[Tweet], embeddings: np.ndarray) -> list[Cluster]:
        """
        Cluster tweets from their embeddings.

        Args:
            tweets:     Scored tweet dicts aligned with embeddings rows.
            embeddings: L2-normalized float32 array, shape (N, D).

        Returns:
            list[Cluster] sorted by size descending, noise cluster last.
        """
        print(f"  UMAP: {embeddings.shape} → (N, {self.umap_components})...")
        reducer = umap.UMAP(
            n_components=self.umap_components,
            random_state=self.random_state,
            metric="cosine",
        )
        with _umap_lock:
            reduced = reducer.fit_transform(embeddings)

        labels, count = self._sweep_hdbscan(reduced, len(tweets))

        groups = self._build_groups(labels, tweets, embeddings)
        real_ids = [label for label in groups if label != -1]

        if count > self.target_max:
            print(f"  Merging {count} → target [{self.target_min}, {self.target_max}]...")
            real_ids = self._merge_to_target(groups, real_ids)
            print(f"  Final cluster count: {len(real_ids)}")

        # Build Cluster objects, deduplicate, sort
        clusters: list[Cluster] = []
        for new_id, orig_id in enumerate(real_ids):
            g = groups[orig_id]
            t, e = self._deduplicate(g["tweets"], g["embeddings"])
            clusters.append(Cluster(id=new_id, tweets=t, embeddings=e))

        if -1 in groups:
            g = groups[-1]
            t, e = self._deduplicate(g["tweets"], g["embeddings"])
            clusters.append(Cluster(id=-1, tweets=t, embeddings=e))

        clusters.sort(key=lambda c: (c["id"] == -1, -len(c["tweets"])))

        n_after_dedup = sum(len(c["tweets"]) for c in clusters)
        print(f"  After dedup: {n_after_dedup} tweets across {len(clusters)} groups")
        return clusters

    # ── helpers ───────────────────────────────────────────────────────────────

    def _sweep_hdbscan(
        self, reduced: np.ndarray, n: int
    ) -> tuple[np.ndarray, int]:
        """
        Try a range of min_cluster_size values with EOM and return the best labeling.

        Priority:
          1. In-range result closest to midpoint of [target_min, target_max]
          2. Overshoot result with fewest clusters (will be merged down)
          3. Undershoot result with most clusters (sparse dataset, warn)
        """
        candidates = self._candidate_values(n)
        print(f"  HDBSCAN sweep over {len(candidates)} min_cluster_size values...")

        in_range:  list[tuple[int, int, np.ndarray]] = []
        overshoot: list[tuple[int, int, np.ndarray]] = []
        undershoot: list[tuple[int, int, np.ndarray]] = []

        for mcs in candidates:
            labels = hdbscan.HDBSCAN(
                min_cluster_size=mcs,
                min_samples=max(1, mcs // 3),
                metric="euclidean",
            ).fit_predict(reduced)
            count = len(set(labels)) - (1 if -1 in labels else 0)
            entry = (count, mcs, labels)

            if self.target_min <= count <= self.target_max:
                in_range.append(entry)
            elif count > self.target_max:
                overshoot.append(entry)
            else:
                undershoot.append(entry)

        if in_range:
            mid = (self.target_min + self.target_max) // 2
            in_range.sort(key=lambda x: abs(x[0] - mid))
            count, mcs, labels = in_range[0]
            print(f"  Selected min_cluster_size={mcs} → {count} clusters")
            return labels, count

        if overshoot:
            overshoot.sort(key=lambda x: x[0])  # fewest excess clusters first
            count, mcs, labels = overshoot[0]
            print(f"  Selected min_cluster_size={mcs} → {count} clusters (will merge down)")
            return labels, count

        undershoot.sort(key=lambda x: -x[0])  # most clusters first
        count, mcs, labels = undershoot[0]
        print(f"  Warning: best result is only {count} clusters (target_min={self.target_min})")
        return labels, count

    def _candidate_values(self, n: int) -> list[int]:
        """Spread of min_cluster_size values mixing relative and absolute sizes."""
        values: set[int] = set()
        for divisor in [4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30, 40, 50]:
            values.add(max(2, n // divisor))
        for v in [2, 3, 4, 5, 6, 8, 10, 12, 15]:
            values.add(v)
        return sorted(values)

    @staticmethod
    def _build_groups(
        labels: np.ndarray, tweets: list[Tweet], embeddings: np.ndarray
    ) -> dict[int, dict]:
        """Group tweets and embeddings by HDBSCAN label."""
        groups: dict[int, dict] = {}
        for idx, label in enumerate(labels):
            label = int(label)
            if label not in groups:
                groups[label] = {"tweets": [], "embeddings": []}
            groups[label]["tweets"].append(tweets[idx])
            groups[label]["embeddings"].append(embeddings[idx])
        for label in groups:
            groups[label]["embeddings"] = np.array(groups[label]["embeddings"])
        return groups

    @staticmethod
    def _cluster_centroid(embeddings: np.ndarray) -> np.ndarray:
        """Re-normalized mean of L2-normalized embedding rows."""
        c = embeddings.mean(axis=0)
        norm = np.linalg.norm(c)
        return c / norm if norm > 0 else c

    def _merge_to_target(self, groups: dict, real_ids: list[int]) -> list[int]:
        """
        Size-penalized greedy merge: repeatedly merges the most similar pair,
        but penalizes merges that would create disproportionately large clusters.
        This prevents one cluster from absorbing most of the dataset.
        """
        target_max = min(self.target_max, len(real_ids))
        if len(real_ids) <= target_max:
            return real_ids

        total_tweets = sum(len(groups[i]["tweets"]) for i in real_ids)
        centroids = {i: self._cluster_centroid(groups[i]["embeddings"]) for i in real_ids}

        while len(real_ids) > target_max:
            best_score, best_i, best_j = -float("inf"), None, None

            for a in range(len(real_ids)):
                for b in range(a + 1, len(real_ids)):
                    i, j = real_ids[a], real_ids[b]
                    sim = float(centroids[i] @ centroids[j])
                    # Penalize merges that would create very large clusters
                    combined_frac = (len(groups[i]["tweets"]) + len(groups[j]["tweets"])) / total_tweets
                    score = sim - 0.4 * combined_frac
                    if score > best_score:
                        best_score, best_i, best_j = score, i, j

            groups[best_i]["tweets"].extend(groups[best_j]["tweets"])
            groups[best_i]["embeddings"] = np.vstack([
                groups[best_i]["embeddings"],
                groups[best_j]["embeddings"],
            ])
            centroids[best_i] = self._cluster_centroid(groups[best_i]["embeddings"])
            del centroids[best_j]
            real_ids = [i for i in real_ids if i != best_j]

        return real_ids

    def _deduplicate(
        self, tweets: list[Tweet], embeddings: np.ndarray
    ) -> tuple[list[Tweet], np.ndarray]:
        """
        Drop near-duplicate tweets (cosine sim > threshold) within a cluster.
        Iterates in importance_score order — keeps the higher-importance copy.
        """
        if len(tweets) <= 1:
            return tweets, embeddings

        order = sorted(
            range(len(tweets)),
            key=lambda i: tweets[i].get("importance_score", 0.0),
            reverse=True,
        )

        kept_indices: list[int] = []
        kept_embeddings: list[np.ndarray] = []

        for i in order:
            emb = embeddings[i]
            if kept_embeddings:
                sims = np.array(kept_embeddings) @ emb  # dot product = cosine (normalized)
                if sims.max() > self.dedup_threshold:
                    continue
            kept_indices.append(i)
            kept_embeddings.append(emb)

        kept_indices_sorted = sorted(kept_indices)
        return (
            [tweets[i] for i in kept_indices_sorted],
            embeddings[kept_indices_sorted],
        )


if __name__ == "__main__":
    from pipeline.score import score_tweets
    from pipeline.embed import Embedder

    input_path = sys.argv[1] if len(sys.argv) > 1 else "timeline_20260313_194631.json"

    with open(input_path) as f:
        raw_tweets = json.load(f)

    tweets = score_tweets(raw_tweets)
    cache_path = Path("cache") / (Path(input_path).stem + "_embeddings.npy")
    embeddings = Embedder().embed(tweets, cache_path=cache_path)

    clusterer = Clusterer()
    clusters = clusterer.cluster(tweets, embeddings)

    n_real = sum(1 for c in clusters if c["id"] != -1)
    n_noise = next((len(c["tweets"]) for c in clusters if c["id"] == -1), 0)

    print(f"\n{'='*60}")
    print(f"{n_real} clusters  |  {n_noise} noise/miscellaneous tweets")
    print(f"{'='*60}\n")

    for cluster in clusters:
        label = "Miscellaneous" if cluster["id"] == -1 else f"Cluster {cluster['id']}"
        top = sorted(cluster["tweets"], key=lambda t: t.get("importance_score", 0), reverse=True)
        print(f"{label}  ({len(cluster['tweets'])} tweets)")
        # for t in top[:15]:
        #     user = t["user"].get("screen_name", "?")
        #     text = t["text"][:90].replace("\n", " ")
        #     url = t.get("url", "")
        #     print(f"  @{user}: {text}")
        #     print(f"    {url}")
        print()
