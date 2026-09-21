"""
Stage 0: Timeline Fetching

Authenticates with X/Twitter via twscrape and fetches the chronological
"Following" timeline (HomeLatestTimeline) for the recent look-back window.
Saves results as a timestamped JSON file.

twscrape has no built-in Following-timeline endpoint, so we add it here: the
current HomeLatestTimeline queryId is discovered from x.com's JavaScript (with a
stored fallback), and pages are pulled over GET through twscrape's private
`_gql_items` pager. See docs/twscrape-migration.md for the full rationale.
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

from dotenv import load_dotenv
from twscrape import API, AccountsPool, NoAccountError
from twscrape.http import make_client
from twscrape.models import Tweet as TwscrapeTweet
from twscrape.utils import get_by_path, to_old_rep
from twscrape.xclid import get_scripts_list, get_tw_page_text

from pipeline.types import Tweet

load_dotenv()

# Resolved relative to project root (where this script is invoked from)
COOKIES_FILE = "cookies.json"

OP_NAME = "HomeLatestTimeline"
# Hardcoded in the twikit fork this app used before; may be stale. Discovery
# from x.com's bundles is preferred; this is only a fallback.
FALLBACK_QUERY_ID = "U0cdisy7QFIoTfu3-Okw0A"
# Internal account name in the per-fetch pool. Not a real X username.
POOL_ACCOUNT = "digest"

DEFAULT_HOURS = 24
DEFAULT_MAX_PAGES = 50

QUERY_ID_RES = [
    re.compile(r'queryId:[`"]([^`"]+)[`"],operationName:[`"]' + OP_NAME + r'[`"]'),
    re.compile(r'params:\{id:[`"]([^`"]+)[`"],[^}]*?name:[`"]' + OP_NAME + r'[`"]'),
]


class SessionExpiredError(Exception):
    """Raised when twscrape marks the account inactive (expired or blocked cookies).

    twscrape does not raise on auth failures — on 401/403 or error codes 32/326 it
    marks the account inactive and quietly stops paging — so we surface it here.
    """


# ── Cookies ──────────────────────────────────────────────────────────────


def cookie_header(cookies) -> str:
    """Build an 'auth_token=…; ct0=…' header from cookies.

    Accepts [{name, value}] (DB / cookies.json format) or {name: value}.
    """
    if isinstance(cookies, list):
        cookies = {c["name"]: c["value"] for c in cookies}
    missing = [k for k in ("auth_token", "ct0") if not cookies.get(k)]
    if missing:
        raise ValueError(f"Missing cookies: {', '.join(missing)}")
    return f"auth_token={cookies['auth_token']}; ct0={cookies['ct0']}"


def _load_cli_cookies() -> list:
    """Load cookies for command-line use from cookies.json."""
    if not os.path.exists(COOKIES_FILE):
        raise ValueError(
            f"No {COOKIES_FILE} found. Create it with your X auth_token and ct0 "
            'as [{"name": "auth_token", "value": "…"}, {"name": "ct0", "value": "…"}].'
        )
    with open(COOKIES_FILE) as f:
        return json.load(f)


# ── Endpoint discovery ───────────────────────────────────────────────────


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


async def resolve_op(query_id: str | None = None) -> str:
    """Return the '<queryId>/HomeLatestTimeline' op string, discovering the id if needed."""
    if not query_id:
        print("Discovering HomeLatestTimeline queryId from x.com bundles...")
        query_id = await discover_query_id()
        if query_id:
            print(f"  found {query_id}")
        else:
            query_id = FALLBACK_QUERY_ID
            print(f"  not found, falling back to {query_id}")
    return f"{query_id}/{OP_NAME}"


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


# ── Fetching ─────────────────────────────────────────────────────────────


async def pages_via_get(api: API, op: str, max_pages: int):
    """GET through twscrape's own pager (retries, account locks, error handling)."""
    n = 0
    async with aclosing(api._gql_items(op, timeline_variables())) as gen:
        async for rep in gen:
            yield rep.json()
            n += 1
            if n >= max_pages:
                return


def timeline_tweets(obj: dict) -> list[TwscrapeTweet]:
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
            out.append(TwscrapeTweet.parse(raw, rep))
        except Exception as e:
            print(f"  ! could not parse tweet {tweet_id}: {type(e).__name__}: {e}")
    return out


async def _collect(pages, cutoff: datetime) -> list[TwscrapeTweet]:
    tweets, page_count = [], 0
    async with aclosing(pages) as gen:
        async for obj in gen:
            page_count += 1
            page_tweets = timeline_tweets(obj)
            total = len(to_old_rep(obj)["tweets"])
            print(f"  page {page_count}: {len(page_tweets)} timeline tweets ({total} in response)")
            for t in page_tweets:
                if t.date >= cutoff:
                    tweets.append(t)
                else:
                    print(f"  reached {t.date:%Y-%m-%d %H:%M} UTC, stopping")
                    return tweets
    return tweets


async def fetch_todays_tweets(
    cookies,
    hours: float = DEFAULT_HOURS,
    max_pages: int = DEFAULT_MAX_PAGES,
    query_id: str | None = None,
) -> list[TwscrapeTweet]:
    """Fetch the Following timeline for the last `hours` hours.

    Creates a temporary, single-account twscrape pool (deleted on exit) so
    concurrent jobs never share credentials. Raises SessionExpiredError if the
    account is marked inactive (expired/blocked cookies), or NoAccountError if the
    only account is rate-limited.
    """
    header = cookie_header(cookies)
    op = await resolve_op(query_id)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    print(f"Fetching tweets since {cutoff:%Y-%m-%d %H:%M} UTC (queryId {op.split('/')[0]})")

    with tempfile.TemporaryDirectory() as tmp:
        pool = AccountsPool(db_file=str(Path(tmp) / "accounts.db"), raise_when_no_account=True)
        await pool.add_account_cookies(POOL_ACCOUNT, header)
        api = API(pool)

        # Stop at the cutoff inside aclosing (in _collect) so the account lock is released.
        tweets = await _collect(pages_via_get(api, op, max_pages), cutoff)

        # twscrape doesn't raise on auth failure; it flips the account inactive.
        acc = await pool.get(POOL_ACCOUNT)
        if not acc.active:
            raise SessionExpiredError(acc.error_msg or "account marked inactive")

    return tweets


# ── Output ───────────────────────────────────────────────────────────────


def tweet_to_dict(t) -> Tweet:
    """Convert a twscrape tweet object to a Tweet dict for JSON serialization."""
    rt = t.retweetedTweet
    return Tweet(
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


def save_tweets(tweets: list, output_dir: str = ".") -> Path:
    """Serialize tweet objects to a timestamped JSON file."""
    now = datetime.now(timezone.utc)
    filename = Path(output_dir) / f"timeline_{now.strftime('%Y%m%d_%H%M%S')}.json"

    data = [tweet_to_dict(t) for t in tweets]
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved {len(tweets)} tweets to {filename}")
    return filename


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--query-id", help="HomeLatestTimeline queryId (skips bundle discovery)")
    ap.add_argument("--hours", type=float, default=DEFAULT_HOURS, help=f"look-back window (default {DEFAULT_HOURS})")
    ap.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="safety cap (~1h of a busy feed per page)")
    ap.add_argument("--out", help="output path (default: timestamped file in the project root)")
    args = ap.parse_args()

    print("X Timeline Fetcher\n")
    try:
        tweets = await fetch_todays_tweets(
            _load_cli_cookies(), hours=args.hours, max_pages=args.max_pages, query_id=args.query_id
        )
    except SessionExpiredError as e:
        print(f"\nFAILED: Twitter session expired or blocked ({e}). Refresh cookies.json.")
        return 1
    except NoAccountError as e:
        print(f"\nFAILED: rate-limited ({e}). Try again later.")
        return 1

    print(f"\nFound {len(tweets)} tweets in the last {args.hours:g}h")
    if not tweets:
        return 1

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps([tweet_to_dict(t) for t in tweets], indent=2, ensure_ascii=False))
        print(f"✓ Saved {len(tweets)} tweets to {args.out}")
    else:
        save_tweets(tweets)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
