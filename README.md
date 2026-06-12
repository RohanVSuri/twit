# X Timeline Digest

## Example
<img width="1438" height="786" alt="Screenshot 2026-06-12 at 4 30 49 PM" src="https://github.com/user-attachments/assets/1c88e42b-3cfa-496d-b9f1-31081ab03caa" />
<img width="1440" height="783" alt="Screenshot 2026-06-12 at 4 31 18 PM" src="https://github.com/user-attachments/assets/aa2f4a68-c19d-4e28-8c3f-b21d451359d1" />

Fetches the last 24 hours of tweets from your Twitter/X following feed and produces a structured digest: topics are clustered, ranked by engagement, and summarized using Claude.

**Pipeline stages**

1. **Fetch** — pulls your chronological timeline via twikit
2. **Score** — ranks tweets by importance (replies × 2 + quotes × 3) / log(followers)
3. **Embed** — sentence-transformer embeddings per tweet
4. **Cluster** — HDBSCAN topic clustering
5. **Summarize** — Claude Haiku writes a summary + bullets per cluster

---

## Running locally

**Requirements:** Python 3.11+, Bun, Docker

### 1. Start the database

```bash
docker-compose up -d
```

### 2. Set up the Python environment

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.development` and fill in the blanks:

```bash
FLASK_APP=app.py
FLASK_RUN_PORT=5001
FLASK_SQLALCHEMY_DATABASE_URI=postgresql://user:password@localhost:5432/timeline

# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=<your-key>

FLASK_SECRET_KEY=<any-random-string>

# Required for the summarize stage
ANTHROPIC_API_KEY=<your-key>
```

### 4. Start the backend

```bash
source venv/bin/activate
flask run
```

Runs on `http://localhost:5001`.

### 5. Start the frontend

```bash
cd frontend
bun install
bun dev
```

Runs on `http://localhost:5173`.

---

## Getting your Twitter cookies

The app authenticates with Twitter using two session cookies. You only need to do this once (or whenever your session expires).

1. Open [twitter.com](https://twitter.com) in Chrome and make sure you're logged in
2. Open DevTools → **Application** → **Cookies** → `https://twitter.com`
3. Find and copy the values for:
  - `auth_token`
  - `ct0`
4. Paste them into the login form at `http://localhost:5173/login`

Cookies are encrypted with Fernet (AES-128) before being stored in the database. Your password is never used or stored.

If you'd like to invalidate these cookies after using the app, you can log out of your X account on [x.com](http://x.com) and log back in. 

---

## Fetching locally, summarizing on a hosted instance

If you want to run just the fetch step on your machine and upload the result to a hosted version of the summarizer:

### 1. Create `cookies.json`

```json
[
  { "name": "auth_token", "value": "your-auth-token" },
  { "name": "ct0", "value": "your-ct0-value" }
]
```

Place it in the project root.

### 2. Run the fetcher

```bash
source venv/bin/activate
python -m pipeline.fetch
```

This produces a file like `timeline_20260603_142500.json` in the project root.

### 3. Upload to the hosted summarizer

Open the hosted app, drag the `timeline_*.json` file into the drop zone, and click **Run**.
