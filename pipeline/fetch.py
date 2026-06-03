"""
Stage 0: Timeline Fetching

Authenticates with X/Twitter via twikit and fetches the chronological
"Following" timeline for today (US Eastern time). Saves results as a timestamped JSON file.
"""

# MONKEY PATCH: Remove this block when twikit is updated to fix ON_DEMAND_FILE_REGEX
# https://github.com/d60/twikit/issues/408#issuecomment-4089055868
import re
_tx_mod = __import__('twikit.x_client_transaction.transaction', fromlist=['ClientTransaction'])
_tx_mod.ON_DEMAND_FILE_REGEX = re.compile(
    r""",(\d+):["']ondemand\.s["']""", flags=(re.VERBOSE | re.MULTILINE))
_tx_mod.ON_DEMAND_HASH_PATTERN = r',{}:"([0-9a-f]+)"'

async def _patched_get_indices(self, home_page_response, session, headers):
    key_byte_indices = []
    response = self.validate_response(home_page_response) or self.home_page_response
    on_demand_file_index = _tx_mod.ON_DEMAND_FILE_REGEX.search(str(response)).group(1)
    regex = re.compile(_tx_mod.ON_DEMAND_HASH_PATTERN.format(on_demand_file_index))
    filename = regex.search(str(response)).group(1)
    on_demand_file_url = f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{filename}a.js"
    on_demand_file_response = await session.request(method="GET", url=on_demand_file_url, headers=headers)
    key_byte_indices_match = _tx_mod.INDICES_REGEX.finditer(str(on_demand_file_response.text))
    for item in key_byte_indices_match:
        key_byte_indices.append(item.group(2))
    if not key_byte_indices:
        raise Exception("Couldn't get KEY_BYTE indices")
    key_byte_indices = list(map(int, key_byte_indices))
    return key_byte_indices[0], key_byte_indices[1:]

_tx_mod.ClientTransaction.get_indices = _patched_get_indices
# END MONKEY PATCH

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from twikit import Client

from pipeline.types import Tweet

load_dotenv()

# Resolved relative to project root (where this script is invoked from)
COOKIES_FILE = "cookies.json"


async def login_and_get_cookies(username: str, email: str, password: str) -> str:
    """
    Authenticate with Twitter and return cookies as a JSON string.
    The password is used only during this call and never persisted.
    """
    client = Client("en-US")
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        await client.login(
            auth_info_1=username,
            auth_info_2=email,
            password=password,
            cookies_file=tmp_path,
        )
        with open(tmp_path) as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def get_client(cookies: dict | None = None) -> Client:
    """
    Return an authenticated twikit Client.

    Accepts cookies dict directly (from DB) for the web flow, or falls back
    to the local cookies.json file for CLI use.
    """
    client = Client("en-US")

    if cookies:
        client.set_cookies(cookies)
    elif os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE) as f:
            cookies_list = json.load(f)
        # twikit expects {"name": "value"} format
        cookies_dict = {c["name"]: c["value"] for c in cookies_list}
        client.set_cookies(cookies_dict)
        print("Loaded saved cookies")
    else:
        print("Logging in (first time)...")
        username = os.getenv("TWITTER_USERNAME")
        email = os.getenv("TWITTER_EMAIL")
        password = os.getenv("TWITTER_PASSWORD")

        if not username or not email or not password:
            raise ValueError(
                "Missing credentials. Set TWITTER_USERNAME, TWITTER_EMAIL, "
                "and TWITTER_PASSWORD in your .env file."
            )

        await client.login(
            auth_info_1=username,
            auth_info_2=email,
            password=password,
            cookies_file=COOKIES_FILE,
        )
        print("Logged in, cookies saved to cookies.json")

    return client


async def fetch_todays_tweets(client: Client) -> list:
    """Fetch all tweets from the last 24 hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    tweets = []

    print(f"\nFetching tweets since {cutoff.strftime('%Y-%m-%d %H:%M')} UTC...")
    results = await client.get_latest_timeline(count=40)

    page = 1
    while results:
        print(f"  Page {page}...")
        for tweet in results:
            tweet_time = tweet.created_at_datetime
            if tweet_time is None:
                continue
            if tweet_time.tzinfo is None:
                tweet_time = tweet_time.replace(tzinfo=timezone.utc)

            if tweet_time >= cutoff:
                tweets.append(tweet)
            else:
                print(f"  Reached {tweet_time.strftime('%Y-%m-%d %H:%M')} UTC, stopping")
                return tweets

        try:
            results = await results.next()
            page += 1
        except Exception as e:
            print(f"  Pagination ended: {e}")
            break

    return tweets


def tweet_to_dict(tweet) -> Tweet:
    """Convert a twikit tweet object to a Tweet dict for JSON serialization."""
    retweeted_text = None
    if tweet.retweeted_tweet:
        retweeted_text = tweet.retweeted_tweet.full_text

    return Tweet(
        id=tweet.id,
        text=tweet.full_text,
        created_at=tweet.created_at,
        created_at_datetime=tweet.created_at_datetime.isoformat() if tweet.created_at_datetime else None,
        lang=tweet.lang,
        favorite_count=tweet.favorite_count,
        retweet_count=tweet.retweet_count,
        reply_count=tweet.reply_count,
        quote_count=tweet.quote_count,
        user=dict(
            id=tweet.user.id if tweet.user else None,
            screen_name=tweet.user.screen_name if tweet.user else None,
            name=tweet.user.name if tweet.user else None,
            followers_count=tweet.user.followers_count if tweet.user else None,
        ),
        is_retweet=tweet.retweeted_tweet is not None,
        retweeted_tweet_id=tweet.retweeted_tweet.id if tweet.retweeted_tweet else None,
        retweeted_tweet_text=retweeted_text,
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


async def main():
    print("X Timeline Fetcher\n")
    client = await get_client()
    tweets = await fetch_todays_tweets(client)

    print(f"\nFound {len(tweets)} tweets from today")
    save_tweets(tweets)


if __name__ == "__main__":
    asyncio.run(main())
