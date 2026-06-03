"""
Stages 4 & 5: Cluster Post-processing and Summarization

Stage 4 — pre-summarization cleanup:
  1. Junk filter: clusters with low avg importance_score → merged into Miscellaneous
  2. Merge check: single Haiku call to identify redundant clusters to combine

Stage 5 — per-cluster summarization:
  One Haiku call per cluster → label + 3–5 sentence narrative + cited tweet IDs
"""

import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

from pipeline.score import embed_text, score_tweets
from pipeline.embed import Embedder
from pipeline.cluster import Clusterer
from pipeline.types import Bullet, Cluster, ClusterSummary, Tweet
from pipeline.prompts import MERGE_CLUSTERS_PROMPT, SUMMARIZE_CLUSTER_PROMPT

import numpy as np

MISC_ID = -1


class Summarizer:
    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        self.model = model
        self._calls = 0

    # ── public API ────────────────────────────────────────────────────────────

    def summarize_all(
        self,
        clusters: list[Cluster],
        min_avg_importance: float = 2.0,
        cache_path: str | Path | None = None,
    ) -> list[ClusterSummary]:
        """
        Full pipeline: filter junk → merge similar → summarize.

        Args:
            clusters:            Output of Clusterer.cluster().
            min_avg_importance:  Clusters below this avg importance_score are
                                 routed to Miscellaneous before any LLM calls.
            cache_path:          If given, load from cache if it exists;
                                 save to disk after summarizing.
        Returns:
            list[ClusterSummary] sorted by tweet_count desc, Miscellaneous last.
        """
        if cache_path is not None:
            cache_path = Path(cache_path)
            if cache_path.exists():
                print(f"  Cache hit — loading summaries from {cache_path}")
                with open(cache_path) as f:
                    return json.load(f)
        real, misc = self._filter_junk(clusters, min_avg_importance)
        print(f"  Junk filter: {len(real)} real clusters, {len(misc)} junk clusters → Misc")

        real = self.merge_clusters(real)
        print(f"  After merge: {len(real)} clusters to summarize")

        summaries: list[ClusterSummary] = []

        # Summarize real clusters
        for i, cluster in enumerate(real):
            print(f"  Summarizing cluster {i+1}/{len(real)} ({len(cluster['tweets'])} tweets)...")
            summary = self.summarize_cluster(cluster)
            summaries.append(summary)

        # Summarize Miscellaneous if non-empty
        all_misc_tweets = misc
        for cl in clusters:
            if cl["id"] == MISC_ID:
                all_misc_tweets = all_misc_tweets + cl["tweets"]
                break
        if all_misc_tweets:
            misc_cluster = Cluster(id=MISC_ID, tweets=all_misc_tweets, embeddings=np.array([]))
            misc_summary = ClusterSummary(
                id=MISC_ID,
                label="Miscellaneous",
                summary="",
                bullets=[],
                tweet_count=len(all_misc_tweets),
                total_importance=0.0,
            )
            summaries.append(misc_summary)

        # Sort: highest total_importance first, Misc last
        summaries.sort(key=lambda s: (s["id"] == MISC_ID, -s["total_importance"]))

        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump(summaries, f, indent=2, ensure_ascii=False)
            print(f"  Saved summaries to {cache_path}")

        return summaries

    def merge_clusters(self, clusters: list[Cluster]) -> list[Cluster]:
        """
        Single Haiku call to identify clusters that should be merged.
        Uses the top tweet per cluster as a cheap proxy label.
        """
        if len(clusters) <= 1:
            return clusters

        labels = {i: self._quick_label(cl) for i, cl in enumerate(clusters)}
        label_list = "\n".join(f"- {label}" for label in labels.values())

        raw = self._call(MERGE_CLUSTERS_PROMPT.format(label_list=label_list))
        try:
            result = json.loads(self._strip_fences(raw))
        except json.JSONDecodeError:
            print("  Warning: merge check JSON parse failed, skipping merges")
            return clusters

        merges = result.get("merges", [])
        if not merges:
            return clusters

        print(f"  Merging {len(merges)} cluster pair(s)...")

        # Build a mapping: quick_label → cluster index
        label_to_idx = {label: i for i, label in labels.items()}
        consumed: set[int] = set()

        for merge_op in merges:
            targets = merge_op.get("merge", [])
            indices = [label_to_idx[t] for t in targets if t in label_to_idx]
            if len(indices) < 2:
                continue
            base = indices[0]
            for extra in indices[1:]:
                if extra in consumed:
                    continue
                clusters[base]["tweets"].extend(clusters[extra]["tweets"])
                # Keep embeddings in sync with tweets
                base_emb = clusters[base]["embeddings"]
                extra_emb = clusters[extra]["embeddings"]
                if len(base_emb) > 0 and len(extra_emb) > 0:
                    clusters[base]["embeddings"] = np.vstack([base_emb, extra_emb])
                elif len(extra_emb) > 0:
                    clusters[base]["embeddings"] = extra_emb
                consumed.add(extra)

        return [cl for i, cl in enumerate(clusters) if i not in consumed]

    def summarize_cluster(self, cluster: Cluster) -> ClusterSummary:
        """One Haiku call to summarize a single cluster."""
        id_to_url = {t["id"]: t.get("url", "") for t in cluster["tweets"]}
        total_importance = sum(t.get("importance_score", 0.0) for t in cluster["tweets"])

        # Sort by importance, cap at 50 tweets to save tokens
        top_tweets = sorted(
            cluster["tweets"],
            key=lambda t: t.get("importance_score", 0),
            reverse=True,
        )[:50]

        # Re-align embeddings to top_tweets order using tweet string ID as key
        top_embeddings = np.array([])
        if len(cluster["embeddings"]) > 0:
            tweet_to_emb = {t["id"]: cluster["embeddings"][i] for i, t in enumerate(cluster["tweets"])}
            rows = [tweet_to_emb[t["id"]] for t in top_tweets if t["id"] in tweet_to_emb]
            if rows:
                top_embeddings = np.array(rows)

        # Group tweets by sub-event, format with importance signal for LLM
        if len(top_embeddings) > 1:
            groups = self._group_by_subevent(top_tweets, top_embeddings)
        else:
            groups = [list(range(len(top_tweets)))]

        # Sort groups by combined importance descending
        groups.sort(
            key=lambda g: sum(top_tweets[i].get("importance_score", 0) for i in g),
            reverse=True,
        )

        # Build grouped tweet_list string
        lines = []
        for group in groups:
            combined = sum(top_tweets[i].get("importance_score", 0) for i in group)
            n = len(group)
            lines.append(f"[SUB-EVENT  combined_importance={combined:.1f}  coverage={n} tweet{'s' if n != 1 else ''}]")
            for i in group:
                t = top_tweets[i]
                lines.append(f"[{t['id']}] {embed_text(t)}")
            lines.append("")

        tweet_list = "\n".join(lines)

        raw = self._call(SUMMARIZE_CLUSTER_PROMPT.format(tweet_list=tweet_list))
        try:
            parsed = json.loads(self._strip_fences(raw))
        except json.JSONDecodeError:
            parsed = {"label": "Unknown", "bullets": []}

        bullets: list[Bullet] = [
            Bullet(
                text=b["text"],
                urls=[id_to_url[sid] for sid in b.get("source_ids", []) if sid in id_to_url],
            )
            for b in parsed.get("bullets", [])
            if b.get("text")
        ]

        return ClusterSummary(
            id=cluster["id"],
            label=parsed.get("label", "Unknown"),
            summary=parsed.get("summary", ""),
            bullets=bullets,
            tweet_count=len(cluster["tweets"]),
            total_importance=total_importance,
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _call(self, prompt: str) -> str:
        self._calls += 1
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    @staticmethod
    def _strip_fences(text: str) -> str:
        return text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    @staticmethod
    def _group_by_subevent(
        tweets: list[Tweet],
        embeddings: np.ndarray,
        sim_threshold: float = 0.75,
    ) -> list[list[int]]:
        """
        Greedy sub-event grouping using cosine similarity on cluster embeddings.
        Each tweet joins the first group whose centroid is within sim_threshold,
        otherwise starts a new group.
        Returns a list of index groups (indices into tweets).
        """
        groups: list[list[int]] = []
        centroids: list[np.ndarray] = []

        for i, emb in enumerate(embeddings):
            best_group = -1
            best_sim = sim_threshold

            for g_idx, centroid in enumerate(centroids):
                sim = float(emb @ centroid)  # dot product on normalized vecs = cosine
                if sim > best_sim:
                    best_sim = sim
                    best_group = g_idx

            if best_group == -1:
                groups.append([i])
                centroids.append(emb.copy())
            else:
                groups[best_group].append(i)
                # Update centroid as mean of group embeddings
                group_embs = embeddings[groups[best_group]]
                centroid = group_embs.mean(axis=0)
                norm = np.linalg.norm(centroid)
                centroids[best_group] = centroid / norm if norm > 0 else centroid

        return groups

    @staticmethod
    def _quick_label(cluster: Cluster) -> str:
        """URL-stripped text of the highest importance_score tweet, ≤120 chars."""
        top = max(cluster["tweets"], key=lambda t: t.get("importance_score", 0.0))
        return embed_text(top)[:120]

    @staticmethod
    def _filter_junk(
        clusters: list[Cluster], min_avg_importance: float
    ) -> tuple[list[Cluster], list[Tweet]]:
        """
        Split clusters into (real, junk_tweets).
        Noise cluster (id=-1) is always excluded from real.
        Clusters below min_avg_importance go to junk.
        """
        real: list[Cluster] = []
        junk_tweets: list[Tweet] = []

        for cl in clusters:
            if cl["id"] == MISC_ID:
                junk_tweets.extend(cl["tweets"])
                continue
            if not cl["tweets"]:
                continue
            avg = sum(t.get("importance_score", 0) for t in cl["tweets"]) / len(cl["tweets"])
            if avg < min_avg_importance:
                junk_tweets.extend(cl["tweets"])
            else:
                real.append(cl)

        return real, junk_tweets


if __name__ == "__main__":
    input_path = sys.argv[1] if len(sys.argv) > 1 else "timeline_20260313_194631.json"

    with open(input_path) as f:
        raw_tweets = json.load(f)

    tweets = score_tweets(raw_tweets)
    cache_path = Path("cache") / (Path(input_path).stem + "_embeddings.npy")
    embeddings = Embedder().embed(tweets, cache_path=cache_path)

    clusters = Clusterer().cluster(tweets, embeddings)

    summary_cache = Path("cache") / (Path(input_path).stem + "_summaries.json")
    summarizer = Summarizer()
    summaries = summarizer.summarize_all(clusters, cache_path=summary_cache)

    print(f"\n{'='*60}")
    print(f"Haiku API calls: {summarizer._calls}")
    print(f"{'='*60}\n")

    for s in summaries:
        print(f"{s['label']}  ({s['tweet_count']} tweets)")
        if s.get("summary"):
            print(f"  {s['summary']}")
            print()
        for b in s["bullets"]:
            print(f"  • {b['text']}")
            for url in b["urls"]:
                print(f"    {url}")
        if not s["bullets"]:
            print("  (no bullets)")
        print()
