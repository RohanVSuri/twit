import json
import time
import threading

from internal.models.job import Job, Step
from flask import current_app

def _run(job_id: str, app) -> None:
    with app.app_context():
        from internal.db import db
        from pipeline.score import score_tweets
        from pipeline.embed import Embedder
        from pipeline.cluster import Clusterer
        from pipeline.summarize import Summarizer

        def get_step(step_key: str) -> Step:
            return db.session.query(Step).filter_by(job_id=job_id, step_key=step_key).one()

        def start_step(step_key: str) -> float:
            step = get_step(step_key)
            step.status = "running"
            db.session.commit()
            return time.time()

        def finish_step(step_key: str, t0: float) -> None:
            step = get_step(step_key)
            step.status = "complete"
            step.elapsed = round(time.time() - t0, 1)
            db.session.commit()

        job = db.session.get(Job, job_id)
        job.status = "running"
        db.session.commit()

        try:
            with open(job.file_path) as f:
                raw_tweets = json.load(f)

            t0 = start_step("score")
            tweets = score_tweets(raw_tweets)
            finish_step("score", t0)

            t0 = start_step("embed")
            embedder = Embedder()
            embeddings = embedder.embed(tweets)
            finish_step("embed", t0)

            t0 = start_step("cluster")
            clusters = Clusterer().cluster(tweets, embeddings)
            finish_step("cluster", t0)

            t0 = start_step("summarize")
            summarizer = Summarizer()
            summaries = summarizer.summarize_all(clusters)
            finish_step("summarize", t0)

            job = db.session.get(Job, job_id)
            job.summaries = [dict(s) for s in summaries]
            job.status = "complete"
            db.session.commit()

        except Exception as exc:
            job = db.session.get(Job, job_id)
            job.status = "error"
            job.error = str(exc)
            for step in job.steps:
                if step.status == "running":
                    step.status = "error"
            db.session.commit()
            raise


def start(job: Job) -> None:
    app = current_app._get_current_object()
    job_id = str(job.id)
    t = threading.Thread(target=_run, args=(job_id, app), daemon=True)
    t.start()
