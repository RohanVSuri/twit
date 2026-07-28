import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import strawberry
from strawberry.file_uploads import Upload

from internal.db import db
from internal.models.job import Job, create_job
from internal.graph.types import AuthResult, JobStatus, StepStatus
import internal.runner as runner

UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads"
SESSION_TOKEN_TTL = timedelta(days=30)


def _job_to_gql(job: Job) -> JobStatus:
    d = job.to_status_dict()
    return JobStatus(
        job_id=d["job_id"],
        status=d["status"],
        steps=[StepStatus(id=s["id"], name=s["name"], status=s["status"], elapsed=s["elapsed"]) for s in d["steps"]],
        progress=d["progress"],
        error=d["error"],
    )


@strawberry.type
class Mutation:
    @strawberry.mutation
    def twitter_login(self, username: str, cookies_json: str) -> AuthResult:
        from internal.models.user import User
        from internal.crypto import encrypt, hash_token

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

        raw_token = str(uuid.uuid4())
        user.cookies_encrypted = encrypt(json.dumps(parsed))
        user.session_token = hash_token(raw_token)
        user.session_token_expires_at = datetime.utcnow() + SESSION_TOKEN_TTL
        db.session.commit()

        return AuthResult(success=True, username=username, session_token=raw_token, error=None)

    @strawberry.mutation
    def twitter_logout(self) -> bool:
        from internal.auth import get_current_user
        user = get_current_user()
        if user:
            user.session_token = None
            user.session_token_expires_at = None
            db.session.commit()
        return True

    @strawberry.mutation
    def fetch_timeline(self) -> JobStatus:
        from internal.auth import get_current_user

        user = get_current_user()
        if not user:
            raise ValueError("Not authenticated")
        if not user.cookies_encrypted:
            raise ValueError("No Twitter credentials stored. Please log in again.")

        job = create_job("", user_id=user.id, include_fetch=True)
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
        from internal.auth import get_current_user
        user = get_current_user()
        if not user:
            raise ValueError("Not authenticated")
        job = db.session.get(Job, str(job_id))
        if not job or job.user_id != user.id:
            raise ValueError(f"Job {job_id} not found")
        if job.status == "queued":
            runner.start(job)
        return _job_to_gql(job)
