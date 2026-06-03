import strawberry

from internal.db import db
from internal.models.job import Job
from internal.graph.types import JobStatus, StepStatus, DigestResult, ClusterSummary, Bullet, UserProfile


@strawberry.type
class Query:
    @strawberry.field
    def me(self) -> UserProfile | None:
        from internal.auth import get_current_user
        user = get_current_user()
        if not user:
            return None
        latest = (
            db.session.query(Job)
            .filter_by(user_id=user.id, status="complete")
            .order_by(Job.created_at.desc())
            .first()
        )
        return UserProfile(
            id=str(user.id),
            twitter_username=user.twitter_username,
            latest_job_id=str(latest.id) if latest else None,
        )

    @strawberry.field
    def job_status(self, job_id: strawberry.ID) -> JobStatus | None:
        job = db.session.get(Job, str(job_id))
        if not job:
            return None
        d = job.to_status_dict()
        return JobStatus(
            job_id=d["job_id"],
            status=d["status"],
            steps=[StepStatus(id=s["id"], name=s["name"], status=s["status"], elapsed=s["elapsed"]) for s in d["steps"]],
            progress=d["progress"],
            error=d["error"],
        )

    @strawberry.field
    def digest(self, job_id: strawberry.ID) -> DigestResult | None:
        job = db.session.get(Job, str(job_id))
        if not job or job.status != "complete" or not job.summaries:
            return None
        clusters = []
        for c in job.summaries:
            bullets = [Bullet(text=b["text"], urls=b["urls"]) for b in c.get("bullets", [])]
            clusters.append(ClusterSummary(
                id=c["id"],
                label=c["label"],
                summary=c["summary"],
                bullets=bullets,
                tweet_count=c["tweet_count"],
                total_importance=c["total_importance"],
            ))
        return DigestResult(clusters=clusters)
