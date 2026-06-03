from internal.db import db

STEP_CONFIGS = [
    ("score",     "SCORING & FILTERING"),
    ("embed",     "EMBEDDING TWEETS"),
    ("cluster",   "CLUSTERING TOPICS"),
    ("summarize", "GENERATING SUMMARIES"),
]


class Step(db.Model):
    __tablename__ = "steps"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.UUID(as_uuid=True), db.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    step_key = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="pending")
    elapsed = db.Column(db.Float, nullable=True)
    position = db.Column(db.Integer, nullable=False)

    def to_dict(self):
        return {
            "id": self.step_key,
            "job_id": self.job_id,
            "step_key": self.step_key,
            "name": self.name,
            "status": self.status,
            "elapsed": self.elapsed,
            "position": self.position
        }


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    user_id = db.Column(db.UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="queued")
    file_path = db.Column(db.Text, nullable=False)
    summaries = db.Column(db.JSON, nullable=True)
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.text("NOW()"))
    updated_at = db.Column(db.DateTime, server_default=db.text("NOW()"))

    steps = db.relationship("Step", backref="job", order_by="Step.position", cascade="all, delete-orphan")

    def to_status_dict(self):
        completed = sum(1 for s in self.steps if s.status == "complete")
        total = len(self.steps)
        progress = int((completed / total) * 100) if total else 0
        if self.status == "complete":
            progress = 100
        return {
            "job_id": str(self.id),
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "progress": progress,
            "error": self.error,
        }


def create_job(file_path: str, user_id=None) -> Job:
    job = Job(file_path=file_path, user_id=user_id)
    db.session.add(job)
    db.session.flush()  # get the UUID assigned
    for i, (key, name) in enumerate(STEP_CONFIGS):
        db.session.add(Step(job_id=job.id, step_key=key, name=name, position=i))
    db.session.commit()
    db.session.refresh(job)
    return job
