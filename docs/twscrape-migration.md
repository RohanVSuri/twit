# twikit → twscrape migration

Status as of 2026-09-13: **research and test fetch done; app code not yet migrated.**

The test fetch (`scripts/twscrape_home_spike.py`) pulled a full 12-hour Following
timeline through twscrape, and the output works with the existing scoring stage.
The remaining work is porting that logic into `pipeline/fetch.py` and
`internal/runner.py`.

---

## 1. Current twikit setup

Only the fetch stage uses twikit. Every later stage reads the tweet JSON
(`pipeline/types.py:Tweet`). The manual upload flow reads the same JSON, so its
keys must stay the same.

| Where | What it does |
|---|---|
| `requirements.txt:1` | Installs a fork of twikit: `PawiX25/twikit@fix/keyerror-optional-fields` |
| `pipeline/fetch.py:8-33` | Monkey patch for twikit's broken request signing (`ON_DEMAND_FILE_REGEX`, issue d60/twikit#408) |
| `pipeline/fetch.py:53` | `login_and_get_cookies`: logs in with a password. Nothing in the app calls it. |
| `pipeline/fetch.py:76` | `get_client`: loads cookies from the database (web) or `cookies.json` (command line), or logs in with a password from env vars |
| `pipeline/fetch.py:117` | `get_latest_timeline(count=40)` (the Following timeline), paging with `.next()` until tweets are older than the cutoff |
| `pipeline/fetch.py:151` | `tweet_to_dict`: converts a twikit tweet into the `Tweet` dict |
| `internal/runner.py:52-69` | Decrypts cookies, then treats errors containing "auth", "401", "unauthorized" or "forbidden" as an expired session and clears the stored cookies |
| `internal/graph/mutations.py:32` | `twitter_login` stores `auth_token` and `ct0`, Fernet-encrypted, as a list of `{name, value}` |

Existing mismatch: `fetch_todays_tweets` uses a **12-hour** cutoff, but its
docstring and the README say 24 hours.

---

## 2. What twscrape offers

Checked against twscrape **v0.20.1** (commit `55ac729`, 2026-08-28).

- Async library with endpoints for search, users, tweets, lists, bookmarks,
  communities and trends.
- **No home or Following timeline endpoint.** There's no `HomeLatestTimeline`
  or `HomeTimeline`, and no GitHub issues ask for one.
- Accounts live in a SQLite pool (`accounts.db` by default) and rotate between
  endpoints. Cookie login uses `pool.add_account_cookies(username,
  "auth_token=…; ct0=…")`.
- Does its own request signing (`xclid.py`), so the twikit monkey patch goes away.
- Its op-ID update script (`scripts/update-gql-ops.py`) only refreshes endpoints
  already listed in twscrape's own `api.py`. **We have to keep our own endpoint ID
  current.**
- Its request client only sends query-string params, so it can't send a POST body.
  twikit calls `HomeLatestTimeline` with POST, but GET turned out to work (see §4).
- **Sends telemetry** (endpoint names) to PostHog. Turn it off with `TWS_TELEMETRY=0`.
- Auth failures **don't raise errors**. On 401, 403 or error codes 32/326 it marks
  the account inactive and quietly ends paging.
- By default it **waits indefinitely** when the only account is rate-limited.
  Setting `raise_when_no_account=True` makes it raise `NoAccountError` instead.

---

## 3. Options considered for the missing Following timeline

| Option | Verdict |
|---|---|
| **Subclass `API` and add `HomeLatestTimeline` via the internal `_gql_items` pager** | **Chosen.** Tested and works over GET. Downsides: `_gql_items` is private (pin the twscrape version), and we maintain the endpoint ID (found automatically from x.com's JavaScript). |
| Upstream PR adding `home_timeline` to twscrape | Cleanest long term. Can run alongside the subclass. |
| `search("filter:follows since:…")` | Uses existing endpoints, but doesn't reliably return the full chronological feed. Rejected. |
| `list_timeline(list_id)` | Rejected. It reads an **X List** (a hand-picked group of accounts with its own feed), not the Following feed. A List mirroring your follows means adding everyone by hand on x.com, or X's list-editing endpoints that twscrape lacks (plus spam-flag risk). Capped at 5,000 members and goes stale as follows change. |

---

## 4. Test script: `scripts/twscrape_home_spike.py`

A standalone script that fetches the Following timeline through twscrape with the
missing endpoint added.

**What it does**

1. Loads cookies from `cookies.json` (gitignored; `[{name, value}]` format) or
   from `TWITTER_AUTH_TOKEN` / `TWITTER_CT0`.
2. Creates a **temporary** twscrape pool, deleted on exit, with telemetry off.
3. Finds the current `HomeLatestTimeline` endpoint ID in x.com's JavaScript.
   Falls back to twikit's hardcoded `U0cdisy7QFIoTfu3-Okw0A`, or takes one from
   `--query-id`.
4. Tries GET through `_gql_items`, then POST with a JSON body if GET fails.
5. Keeps only real timeline tweets, in order (see findings), and stops at the cutoff.
6. Reports whether twscrape marked the account inactive (how expired cookies show up).
7. Prints a summary. Optionally writes app-compatible JSON (`--out`) and saves
   raw pages (`--dump-raw`).

**Usage**

```bash
source .venv/bin/activate          # Python 3.10+, pip install twscrape==0.20.1
python scripts/twscrape_home_spike.py --cookies cookies.json --out uploads/timeline_twscrape.json
# flags: --method auto|get|post  --hours 12  --max-pages 50  --query-id ID  --dump-raw DIR  --verbose
```

### Findings from the runs

| Run | Result | Cause / fix |
|---|---|---|
| 1 | GET worked, but page 1 had **143 tweets** (40 requested), stopped at a Sep 3 tweet, and only 12 made the window. Then `--out` crashed. | twscrape's `parse_tweets()` returns **every tweet nested anywhere in the response** (quoted tweets, thread context), unordered, and drops tweets retweeted elsewhere on the page. **Fix:** walk the timeline `entries` in order and parse only single-tweet entries (`content.itemContent`), like twikit. The crash was `uploads/` not existing; the script now creates it. |
| 2 | 88 timeline tweets, but only **5** in the window, then stopped at a Sep 7 tweet. | Unknown until the raw page was dumped. |
| 3 (with `--dump-raw`, 1 page) | 2 tweets, then stopped at a May 18 tweet. | Raw dump showed every out-of-order entry is an **ad**: `entryId` starts with `promoted-tweet-`, it carries `promotedMetadata`, and it keeps its original (months-old) date. X inserts ads even with `includePromotedContent: False`. Apart from ads, entries are strictly newest-first. **Fix:** skip promoted entries. |
| 4 (full) | **1,195 tweets**, 15 pages, 13:57 → 01:56 UTC (12h), 291 retweets, 257 authors | Works. |

Other observations from the raw page:

- One page (`count: 40`) returns about 100 entries and covers roughly an hour of a
  busy feed. 12 hours took 15 pages, so the default `--max-pages` went from 10 to 50,
  with a warning if the cap is hit.
- About 15–20% of entries per page are `home-conversation-*` **thread modules**
  (threads and replies from followed accounts). These are skipped, just as the
  current twikit code skips them. Could be added later.
- Structure: one `TimelineAddEntries` instruction, `cursor-top` / `cursor-bottom`
  entries, and descending `sortIndex`.

### Output validation (run 4 file)

- 1,195 unique IDs, **0 duplicates**.
- 0 missing `text`, `created_at`, `created_at_datetime`, `lang`,
  `user.screen_name`, `user.name` or `user.followers_count`. Every retweet has
  `retweeted_tweet_text`.
- `pipeline.score.score_tweets` runs on it unchanged: 291 retweets and 56
  image/link-only tweets filtered, **848 scored**, and the top-importance tweets
  look sensible.
- **Not yet tried:** embed, cluster and summarize (they need the full app
  environment). Next step: upload the file in the app.

---

## 5. Field mapping (twikit → twscrape)

| `Tweet` key | twikit | twscrape |
|---|---|---|
| `id` | `id` | `id_str` (keep it a string; summarize looks tweets up by string ID) |
| `text` | `full_text` | `rawContent` (includes the full text of long posts) |
| `created_at` | `created_at` | `date.strftime("%a %b %d %H:%M:%S %z %Y")` |
| `created_at_datetime` | `created_at_datetime` | `date.isoformat()` (timezone-aware UTC) |
| `lang` | `lang` | `lang` |
| `favorite_count` / `retweet_count` / `reply_count` / `quote_count` | same | `likeCount` / `retweetCount` / `replyCount` / `quoteCount` |
| `user.id` / `screen_name` / `name` / `followers_count` | same | `user.id_str` / `username` / `displayname` / `followersCount` |
| `is_retweet`, `retweeted_tweet_id`, `retweeted_tweet_text` | `retweeted_tweet` | `retweetedTweet` (`id_str`, `rawContent`) |
| `url` (new) | n/a | `url` (`score.py` keeps it if present) |

Also available and unused so far: `bookmarkedCount` and `viewCount`. The note in
`score.py:18` saying these aren't available would become outdated.

---

## 6. Migration plan (remaining work)

**`requirements.txt`**
- Replace the twikit fork with `twscrape==0.20.1` (pinned, because we rely on `_gql_items`).

**`pipeline/fetch.py`**
- Remove the monkey patch, `login_and_get_cookies` and the env-var password login.
- Add the `HomeLatestTimeline` subclass, endpoint-ID discovery (with a stored
  fallback), and GET paging via `_gql_items`.
- Port `timeline_tweets()` from the test script: walk entries in order, **skip
  `promoted-*`**, keep `itemContent` tweets, parse with `Tweet.parse` on
  `to_old_rep`. **Don't** use `parse_tweets()`.
- Stop at the cutoff inside `aclosing(...)` so the account lock is released.
- Port `tweet_to_dict` using the mapping above.
- Set `TWS_TELEMETRY=0` before importing twscrape.
- Keep command-line use working (`cookies.json`, `python -m pipeline.fetch`).

**`internal/runner.py`**
- Create a **temporary pool per job** (temp SQLite file) holding only that user's
  cookies, so users never share accounts.
- `raise_when_no_account=True`; catch `NoAccountError`.
- Detect expired sessions by checking `pool.get(username).active` / `error_msg`
  after fetching, **not** by error text (twscrape doesn't raise). Clear
  `cookies_encrypted` and raise "Twitter session expired" as today.
- Treat 0 fetched tweets as an error instead of running the pipeline on empty input.

**Docs**
- README (twscrape in "Pipeline stages", setup notes), the `score.py` note, the
  `types.py` comment, and fix the 12h/24h mismatch.

**No changes needed:** `twitter_login` mutation, frontend, score/embed/cluster/summarize.

---

## 7. Open questions / follow-ups

- **Possible existing bug in the twikit version:** its loop also stops at the first
  old tweet and doesn't obviously skip ads, so current digests may be cut short.
  Not verified.
- **Thread modules:** include `home-conversation-*` tweets in the digest? They're
  skipped today in both versions.
- **Endpoint ID drift:** discovering it at fetch time adds page loads per job.
  Could cache it and refresh only on failure.
- **Upstream:** consider a PR adding `home_timeline` to twscrape to drop the
  reliance on its private pager.
- **Rate limits:** a 12h fetch of a busy feed took 15 requests. Not yet tested
  with several jobs back to back.

---

## Files touched so far

| File | Status |
|---|---|
| `scripts/twscrape_home_spike.py` | New: test script |
| `cookies.json` | New, gitignored: local cookies for the test script |
| `uploads/timeline_twscrape.json` | New, gitignored: output of the full run (1,195 tweets) |
| `docs/twscrape-migration.md` | This document |

App code (`pipeline/`, `internal/`, `frontend/`, `requirements.txt`) is **unchanged**.
