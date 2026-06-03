"""
Stage 1: Engagement Scoring

Two scores per tweet:

  importance_score  — "did this make people think/respond?"
      = (replies * 2 + quotes * 3) / log10(max(followers, 100))
      Replies and quotes require substantive effort; dividing by log(followers)
      normalizes for account size — 50 replies on a 500-follower account is
      extraordinary, 50 replies on a 10M-follower account is noise.

  popularity_score  — raw viral reach
      = likes * 1.0 + retweets * 1.5

The digest pipeline uses importance_score to select representative tweets per
cluster. popularity_score is stored for reference.

Note: twikit doesn't expose bookmark_count or impression_count.
Retweets (is_retweet=True) are filtered out before scoring.
"""

import math
import re

from pipeline.types import Tweet

# Matches t.co URLs (and bare URLs generally)
_URL_RE = re.compile(r"https?://\S+")

# Minimum number of non-whitespace characters remaining after stripping URLs
# for a tweet to be considered embeddable.
MIN_TEXT_CHARS = 15


def embed_text(tweet: Tweet) -> str:
    """strip all urls, gets rid of non-text content"""
    return _URL_RE.sub("", tweet.get("text", "")).strip()


def has_embed_text(tweet: Tweet) -> bool:
    """True if the tweet has enough non-URL text to embed meaningfully."""
    return len(embed_text(tweet).replace(" ", "")) >= MIN_TEXT_CHARS


def compute_importance(tweet: Tweet) -> float:
    replies = (tweet.get("reply_count") or 0) * 2.0
    quotes = (tweet.get("quote_count") or 0) * 3.0
    followers = tweet.get("user", {}).get("followers_count") or 0
    # log10 normalization — floor at 100 followers to avoid division oddities
    follower_factor = math.log10(max(followers, 100))
    return (replies + quotes) / follower_factor


def compute_popularity(tweet: Tweet) -> float:
    likes = (tweet.get("favorite_count") or 0) * 1.0
    retweets = (tweet.get("retweet_count") or 0) * 1.5
    return likes + retweets


def score_tweets(tweets: list[Tweet]) -> list[Tweet]:
    """
    Filter out retweets, then enrich each remaining tweet dict with:
      - importance_score  (discussion-normalized by author size)
      - popularity_score  (raw viral reach)
      - url               (constructed from id if not already present)

    Returns a new list of enriched tweet dicts (originals are not mutated).
    """
    enriched = []
    skipped_retweets = 0
    skipped_no_text = 0

    for tweet in tweets:
        if tweet.get("is_retweet"):
            skipped_retweets += 1
            continue

        if not has_embed_text(tweet):
            skipped_no_text += 1
            continue

        t = dict(tweet)

        if not t.get("url"):
            t["url"] = f"https://twitter.com/i/web/status/{t['id']}"

        t["importance_score"] = compute_importance(t)
        t["popularity_score"] = compute_popularity(t)

        enriched.append(t)

    if skipped_retweets:
        print(f"  Filtered {skipped_retweets} retweets, {skipped_no_text} image/URL-only tweets ({len(enriched)} remain)")

    return enriched


if __name__ == "__main__":
    import json
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "timeline_20260313_194631.json"
    with open(path) as f:
        tweets = json.load(f)

    scored = score_tweets(tweets)

    importance = [t["importance_score"] for t in scored]
    popularity = [t["popularity_score"] for t in scored]
    print(f"\nTweets after filtering: {len(scored)}")
    print(f"Max importance:  {max(importance):.2f}  |  Max popularity:  {max(popularity):.0f}")
    print(f"Mean importance: {sum(importance)/len(importance):.3f}  |  Mean popularity: {sum(popularity)/len(popularity):.1f}")

    print("\nTop 10 by IMPORTANCE (discussion-normalized):")
    for t in sorted(scored, key=lambda t: t["importance_score"], reverse=True)[:10]:
        user = t.get("user", {}).get("screen_name", "?")
        followers = t.get("user", {}).get("followers_count", 0)
        text = t["text"][:80].replace("\n", " ")
        print(f"  [{t['importance_score']:.2f}] @{user} ({followers:,} followers): {text}")

    print("\nTop 10 by POPULARITY (raw viral reach):")
    for t in sorted(scored, key=lambda t: t["popularity_score"], reverse=True)[:10]:
        user = t.get("user", {}).get("screen_name", "?")
        followers = t.get("user", {}).get("followers_count", 0)
        text = t["text"][:80].replace("\n", " ")
        print(f"  [{t['popularity_score']:.0f}] @{user} ({followers:,} followers): {text}")
