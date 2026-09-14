# /// script
# requires-python = ">=3.10"
# dependencies = ["twscrape==0.20.1"]
# ///
"""
Spike: fetch the chronological "Following" timeline (HomeLatestTimeline) with
twscrape, which has no built-in method for it.

Tries GET through twscrape's pager first, then falls back to POST (how twikit
calls this endpoint). Prints a summary and optionally writes the result in the
same JSON format as pipeline/fetch.py so it can be uploaded to the app.

Usage:
  python scripts/twscrape_home_spike.py --cookies cookies.json
  TWITTER_AUTH_TOKEN=... TWITTER_CT0=... python scripts/twscrape_home_spike.py
  python scripts/twscrape_home_spike.py --method post --out timeline_twscrape.json
"""

import os

os.environ.setdefault("TWS_TELEMETRY", "0")  # must be set before twscrape is imported

import argparse
import asyncio
import json
import re
import sys
import tempfile
from contextlib import aclosing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from twscrape import API, AccountsPool, NoAccountError, set_log_level
from twscrape.api import GQL_FEATURES, GQL_URL
from twscrape.http import make_client
from twscrape.models import Tweet
from twscrape.queue_client import AbortReqError, HandledError, QueueClient, XClIdGenStore
from twscrape.utils import get_by_path, to_old_rep
from twscrape.xclid import get_scripts_list, get_tw_page_text

OP_NAME = "HomeLatestTimeline"
# Hardcoded in the twikit fork this app uses; may be stale.
FALLBACK_QUERY_ID = "U0cdisy7QFIoTfu3-Okw0A"
SPIKE_USERNAME = "spike"

QUERY_ID_RES = [
    re.compile(r'queryId:[`"]([^`"]+)[`"],operationName:[`"]' + OP_NAME + r'[`"]'),
    re.compile(r'params:\{id:[`"]([^`"]+)[`"],[^}]*?name:[`"]' + OP_NAME + r'[`"]'),
]


# ── Setup ────────────────────────────────────────────────────────────────


def load_cookie_header(path: str | None) -> str:
    if path:
        raw = json.loads(Path(path).read_text())
        # Accept [{name, value}] (README / DB format) or {name: value}
        cookies = {c["name"]: c["value"] for c in raw} if isinstance(raw, list) else raw
    else:
        cookies = {"auth_token": os.getenv("TWITTER_AUTH_TOKEN"), "ct0": os.getenv("TWITTER_CT0")}

    missing = [k for k in ("auth_token", "ct0") if not cookies.get(k)]
    if missing:
        sys.exit(f"Missing cookies: {', '.join(missing)}. Pass --cookies or set TWITTER_AUTH_TOKEN / TWITTER_CT0.")
    return f"auth_token={cookies['auth_token']}; ct0={cookies['ct0']}"


async def discover_query_id() -> str | None:
    """Scan x.com's JS bundles for the current HomeLatestTimeline queryId."""
    async with make_client() as clt:
        urls: list[str] = []
        for page in ("https://x.com/home", "https://x.com/xdevelopers"):
            try:
                urls.extend(get_scripts_list(await get_tw_page_text(page, clt)))
            except Exception as e:
                print(f"  ! could not load {page}: {e}")

        for url in dict.fromkeys(urls):
            try:
                text = (await clt.request("GET", url)).text
            except Exception:
                continue
            for rx in QUERY_ID_RES:
                if m := rx.search(text):
                    return m.group(1)
    return None


def timeline_variables(cursor: str | None = None) -> dict:
    kv = {
        "count": 40,
        "includePromotedContent": False,
        "latestControlAvailable": True,
        "requestContext": "launch",
        "withCommunity": True,
        "seenTweetIds": [],
    }
    if cursor:
        kv["cursor"] = cursor
    return kv


# ── Fetchers ─────────────────────────────────────────────────────────────


async def pages_via_get(api: API, op: str, max_pages: int):
    """GET through twscrape's own pager (retries, account locks, error handling)."""
    n = 0
    async with aclosing(api._gql_items(op, timeline_variables())) as gen:
        async for rep in gen:
            yield rep.json()
            n += 1
            if n >= max_pages:
                return


async def pages_via_post(api: API, op: str, max_pages: int):
    """POST with a JSON body. twscrape's QueueClient only sends query params, so
    this drives its account context directly while reusing its error checks."""
    url = f"{GQL_URL}/{op}"
    path = urlparse(url).path
    cursor = None

    async with QueueClient(api.pool, OP_NAME, api.debug, proxy=api.proxy) as client:
        for _ in range(max_pages):
            ctx = await client._get_ctx()
            if ctx is None:
                return

            gen = await XClIdGenStore.get(ctx.acc.username, proxy=ctx.proxy, cookies=ctx.acc.cookies)
            body = {
                "variables": timeline_variables(cursor),
                "features": GQL_FEATURES,
                "queryId": op.split("/")[0],
            }
            rep = await ctx.clt.request(
                "POST", url, json=body, headers={"x-client-transaction-id": gen.calc("POST", path)}
            )
            try:
                await client._check_rep(rep)
            except (HandledError, AbortReqError):
                print(f"  ! POST rejected: HTTP {rep.status_code} {rep.text[:300]}")
                return
            ctx.req_count += 1

            obj = rep.json()
            yield obj
            cursor = api._get_cursor(obj)
            if not cursor:
                return


def timeline_tweets(obj: dict) -> list[Tweet]:
    """
    Top-level tweets in timeline order, matching twikit: only single-tweet entries
    (content.itemContent), skipping conversation modules.

    twscrape's parse_tweets() can't be used here: it returns every tweet in the
    response (quoted tweets, thread context) unordered, and drops tweets that were
    retweeted elsewhere on the page.
    """
    rep = to_old_rep(obj)
    out = []
    for entry in get_by_path(obj, "entries") or []:
        item = entry.get("content", {}).get("itemContent") or {}
        # Ads are injected even with includePromotedContent=False, carry their
        # original (often months-old) date, and would trip the cutoff.
        if entry.get("entryId", "").startswith("promoted-") or item.get("promotedMetadata"):
            continue
        result = get_by_path(item, "tweet_results") or {}
        result = result.get("result", {})
        tweet_id = result.get("rest_id") or result.get("tweet", {}).get("rest_id")
        raw = rep["tweets"].get(tweet_id) if tweet_id else None
        if raw is None:
            continue
        try:
            out.append(Tweet.parse(raw, rep))
        except Exception as e:
            print(f"  ! could not parse tweet {tweet_id}: {type(e).__name__}: {e}")
    return out


async def collect(pages, cutoff: datetime, dump_dir: str | None = None) -> tuple[list, int]:
    tweets, page_count = [], 0
    async with aclosing(pages) as gen:
        async for obj in gen:
            page_count += 1
            if dump_dir:
                Path(dump_dir).mkdir(parents=True, exist_ok=True)
                Path(dump_dir, f"page_{page_count}.json").write_text(json.dumps(obj, indent=1))
            page_tweets = timeline_tweets(obj)
            total = len(to_old_rep(obj)["tweets"])
            print(f"  page {page_count}: {len(page_tweets)} timeline tweets ({total} tweets in response)")
            for t in page_tweets:
                if t.date >= cutoff:
                    tweets.append(t)
                else:
                    print(f"  reached {t.date:%Y-%m-%d %H:%M} UTC, stopping")
                    return tweets, page_count
    return tweets, page_count


# ── Output ───────────────────────────────────────────────────────────────


def tweet_to_dict(t) -> dict:
    """Same shape as pipeline/fetch.py:tweet_to_dict (pipeline.types.Tweet)."""
    rt = t.retweetedTweet
    return dict(
        id=t.id_str,
        text=t.rawContent,
        created_at=t.date.strftime("%a %b %d %H:%M:%S %z %Y"),
        created_at_datetime=t.date.isoformat(),
        lang=t.lang,
        favorite_count=t.likeCount,
        retweet_count=t.retweetCount,
        reply_count=t.replyCount,
        quote_count=t.quoteCount,
        user=dict(
            id=t.user.id_str,
            screen_name=t.user.username,
            name=t.user.displayname,
            followers_count=t.user.followersCount,
        ),
        is_retweet=rt is not None,
        retweeted_tweet_id=rt.id_str if rt else None,
        retweeted_tweet_text=rt.rawContent if rt else None,
        url=t.url,
    )


def print_summary(tweets: list) -> None:
    print(f"\n{len(tweets)} tweets in window")
    if not tweets:
        return
    dates = sorted(t.date for t in tweets)
    retweets = sum(1 for t in tweets if t.retweetedTweet)
    authors = len({t.user.username for t in tweets})
    print(f"  range:    {dates[0]:%Y-%m-%d %H:%M} → {dates[-1]:%Y-%m-%d %H:%M} UTC")
    print(f"  retweets: {retweets}   distinct authors: {authors}")
    print("  newest 5:")
    for t in sorted(tweets, key=lambda t: t.date, reverse=True)[:5]:
        text = t.rawContent[:90].replace("\n", " ")
        print(f"    {t.date:%H:%M} @{t.user.username}: {text}")


# ── Main ─────────────────────────────────────────────────────────────────


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cookies", help="cookies.json ([{name, value}] or {name: value})")
    ap.add_argument("--query-id", help="HomeLatestTimeline queryId (skips bundle discovery)")
    ap.add_argument("--method", choices=["auto", "get", "post"], default="auto")
    ap.add_argument("--hours", type=float, default=12, help="look-back window (default 12, same as fetch.py)")
    ap.add_argument("--max-pages", type=int, default=50, help="safety cap (~1h of a busy feed per page)")
    ap.add_argument("--out", help="write tweets as app-compatible timeline JSON")
    ap.add_argument("--dump-raw", metavar="DIR", help="save each raw response page as JSON")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.verbose:
        set_log_level("DEBUG")

    cookie_header = load_cookie_header(args.cookies)

    query_id = args.query_id
    if not query_id:
        print("Discovering HomeLatestTimeline queryId from x.com bundles...")
        query_id = await discover_query_id()
        if query_id:
            print(f"  found {query_id}")
        else:
            query_id = FALLBACK_QUERY_ID
            print(f"  not found, falling back to twikit's {query_id}")
    op = f"{query_id}/{OP_NAME}"

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    print(f"Fetching tweets since {cutoff:%Y-%m-%d %H:%M} UTC")

    with tempfile.TemporaryDirectory() as tmp:
        pool = AccountsPool(db_file=str(Path(tmp) / "accounts.db"), raise_when_no_account=True)
        await pool.add_account_cookies(SPIKE_USERNAME, cookie_header)
        api = API(pool)

        methods = ["get", "post"] if args.method == "auto" else [args.method]
        tweets, used = [], None
        for method in methods:
            print(f"\n[{method.upper()}]")
            fetcher = pages_via_get if method == "get" else pages_via_post
            try:
                tweets, pages = await collect(fetcher(api, op, args.max_pages), cutoff, args.dump_raw)
            except NoAccountError as e:
                print(f"  ! {e}")
                pages = 0
            except Exception as e:
                print(f"  ! {type(e).__name__}: {e}")
                pages = 0

            acc = await pool.get(SPIKE_USERNAME)
            if not acc.active:
                print(f"  ! account marked inactive: {acc.error_msg or '(no message)'}")
                print("    cookies are likely expired or blocked; stopping")
                break
            if pages:
                used = method
                if pages >= args.max_pages and tweets and min(t.date for t in tweets) >= cutoff:
                    print(f"  ! hit --max-pages={args.max_pages} before reaching the cutoff; window is incomplete")
                break
            # The account may have been locked by a failed attempt; clear it before retrying.
            await pool.reset_locks()

    if not used:
        print("\nFAILED: no pages returned by any method. Re-run with --verbose for request logs.")
        return 1

    print(f"\nOK via {used.upper()} (queryId {query_id})")
    print_summary(tweets)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps([tweet_to_dict(t) for t in tweets], indent=2, ensure_ascii=False))
        print(f"\nWrote {args.out}. Upload it in the app to check the rest of the pipeline.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
