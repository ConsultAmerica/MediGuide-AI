"""FastAPI dependency that resolves the signed-in user for record APIs.

Every route that reads or writes a health record takes
``user: User = Depends(require_user)`` and scopes its queries by
``user.id``. A record owned by someone else is reported as 404, never 403,
so record ids can't be probed for existence.
"""

from __future__ import annotations

from fastapi import Request

from src.auth.service import resolve_token
from src.database.models import User
from src.database.session import session_scope
from src.shared.errors import MediGuideError


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return token.strip()


def require_user(request: Request) -> User:
    token = bearer_token(request)
    if not token:
        raise MediGuideError("AUTH_REQUIRED", "Sign in to continue.", status_code=401)
    with session_scope() as session:
        user = resolve_token(session, token)
    if user is None:
        raise MediGuideError(
            "SESSION_EXPIRED",
            "Your session has ended. Sign in again to continue.",
            status_code=401,
        )
    return user


def not_found(what: str) -> MediGuideError:
    return MediGuideError("NOT_FOUND", f"{what} not found.", status_code=404)
