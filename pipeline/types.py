"""
Shared type definitions for the tweet digest pipeline.

Tweet objects flow through all stages as plain dicts (easy JSON
serialization), but TypedDicts give us IDE support and a documented
contract without any runtime overhead.
"""

from typing import Any, TypedDict


class TweetUser(TypedDict, total=False):
    id: str
    screen_name: str
    name: str
    followers_count: int | None


class Tweet(TypedDict, total=False):
    # ── Core fields from twikit export ──────────────────────────────────
    id: str
    text: str
    created_at: str
    created_at_datetime: str | None
    lang: str | None
    favorite_count: int
    retweet_count: int
    reply_count: int
    quote_count: int
    user: TweetUser
    is_retweet: bool
    retweeted_tweet_id: str | None
    retweeted_tweet_text: str | None
    # ── Added by pipeline/score.py ───────────────────────────────────────
    url: str
    importance_score: float
    popularity_score: float


class Cluster(TypedDict):
    id: int              # HDBSCAN label (-1 = miscellaneous / noise)
    tweets: list[Tweet]
    embeddings: Any      # np.ndarray rows for this cluster (float32, L2-normalized)


class Bullet(TypedDict):
    text: str         # one specific event, 1–2 sentences
    urls: list[str]   # source tweet URLs (may be multiple if synthesized)


class ClusterSummary(TypedDict):
    id: int
    label: str             # e.g. "Iran War & Oil"
    summary: str           # 3-5 sentence overview of the most important news
    bullets: list[Bullet]
    tweet_count: int       # number of tweets in cluster after dedup
    total_importance: float  # Σ importance_score — used for inter-cluster ranking
