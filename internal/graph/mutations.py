import asyncio
import json
import uuid
from pathlib import Path

import strawberry
from strawberry.file_uploads import Upload

from internal.db import db
from internal.models.job import Job, create_job
from internal.graph.types import AuthResult, JobStatus, StepStatus
import internal.runner as runner

UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads"


def _job_to_gql(job: Job) -> JobStatus:
    d = job.to_status_dict()
    return JobStatus(
        job_id=d["job_id"],
        status=d["status"],
        steps=[StepStatus(id=s["id"], name=s["name"], status=s["status"], elapsed=s["elapsed"]) for s in d["steps"]],
        progress=d["progress"],
        error=d["error"],
    )


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@strawberry.type
class Mutation:
    @strawberry.mutation
    def twitter_login(self, username: str, cookies_json: str) -> AuthResult:
        from internal.models.user import User
        from internal.crypto import encrypt

        try:
            parsed = json.loads(cookies_json)
            # Normalise: accept either [{name, value}] list or {name: value} dict
            if isinstance(parsed, dict):
                parsed = [{"name": k, "value": v} for k, v in parsed.items()]
            if not isinstance(parsed, list) or not parsed:
                raise ValueError("Expected a JSON array of cookie objects")
        except (json.JSONDecodeError, ValueError) as e:
            return AuthResult(success=False, username=None, session_token=None, error=f"Invalid cookies: {e}")

        user = db.session.query(User).filter_by(twitter_username=username).first()
        if not user:
            user = User(twitter_username=username)
            db.session.add(user)

        user.cookies_encrypted = encrypt(json.dumps(parsed))
        user.session_token = str(uuid.uuid4())
        db.session.commit()

        return AuthResult(success=True, username=username, session_token=user.session_token, error=None)

    @strawberry.mutation
    def twitter_logout(self) -> bool:
        from internal.auth import get_current_user
        user = get_current_user()
        if user:
            user.session_token = None
            db.session.commit()
        return True

    @strawberry.mutation
    def fetch_timeline(self) -> JobStatus:
        from internal.auth import get_current_user
        from internal.crypto import decrypt
        from pipeline.fetch import get_client, fetch_todays_tweets, save_tweets

        user = get_current_user()
        if not user:
            raise ValueError("Not authenticated")
        if not user.cookies_encrypted:
            raise ValueError("No Twitter credentials stored. Please log in again.")

        cookies_list = json.loads(decrypt(user.cookies_encrypted))
        cookies_dict = {c["name"]: c["value"] for c in cookies_list}

        async def _fetch():
            client = await get_client(cookies=cookies_dict)
            tweets = await fetch_todays_tweets(client)
            UPLOADS_DIR.mkdir(exist_ok=True)
            return save_tweets(tweets, output_dir=str(UPLOADS_DIR))

        try:
            file_path = _run_async(_fetch())
        except Exception as e:
            msg = str(e)
            if any(k in msg.lower() for k in ("auth", "401", "unauthorized", "forbidden")):
                user.cookies_encrypted = None
                db.session.commit()
                raise ValueError("Twitter session expired. Please log in again.")
            raise

        job = create_job(str(file_path), user_id=user.id)
        runner.start(job)
        return _job_to_gql(job)

    @strawberry.mutation
    def upload_timeline(self, file: Upload) -> JobStatus:
        from internal.auth import get_current_user
        UPLOADS_DIR.mkdir(exist_ok=True)
        filename = f"{uuid.uuid4()}_{file.filename}"
        dest = UPLOADS_DIR / filename
        dest.write_bytes(file.read())
        current_user = get_current_user()
        job = create_job(str(dest), user_id=current_user.id if current_user else None)
        return _job_to_gql(job)

    @strawberry.mutation
    def run_pipeline(self, job_id: strawberry.ID) -> JobStatus:
        job = db.session.get(Job, str(job_id))
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status == "queued":
            runner.start(job)
        return _job_to_gql(job)
