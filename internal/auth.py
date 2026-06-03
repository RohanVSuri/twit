from flask import request
from internal.db import db
from internal.models.user import User


def get_current_user() -> User | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    return db.session.query(User).filter_by(session_token=token).first()
