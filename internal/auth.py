from datetime import datetime

from flask import request
from internal.crypto import hash_token
from internal.db import db
from internal.models.user import User


def get_current_user() -> User | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    user = db.session.query(User).filter_by(session_token=hash_token(token)).first()
    if not user:
        return None
    if user.session_token_expires_at and user.session_token_expires_at < datetime.utcnow():
        return None
    return user
