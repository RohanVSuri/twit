import strawberry


@strawberry.type
class AuthResult:
    success: bool
    username: str | None
    session_token: str | None
    error: str | None


@strawberry.type
class UserProfile:
    id: strawberry.ID
    twitter_username: str
    latest_job_id: str | None


@strawberry.type
class StepStatus:
    id: str
    name: str
    status: str
    elapsed: float | None


@strawberry.type
class JobStatus:
    job_id: strawberry.ID
    status: str
    steps: list[StepStatus]
    progress: int
    error: str | None


@strawberry.type
class Bullet:
    text: str
    urls: list[str]


@strawberry.type
class ClusterSummary:
    id: int
    label: str
    summary: str
    bullets: list[Bullet]
    tweet_count: int
    total_importance: float


@strawberry.type
class DigestResult:
    clusters: list[ClusterSummary]
