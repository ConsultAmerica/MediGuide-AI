"""Accounts, password hashing, and bearer sessions.

Passwords use stdlib scrypt (no extra dependency). Session tokens are random
and only their SHA-256 is stored, so the auth_sessions table never holds a
usable credential.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import AuthSession, User

SESSION_DAYS = int(os.getenv("AUTH_SESSION_DAYS", "14"))
GUEST_SESSION_DAYS = int(os.getenv("AUTH_GUEST_SESSION_DAYS", "7"))
MIN_PASSWORD_LENGTH = 10

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    # SQLite drops tzinfo on the way back out; every stored value is UTC.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt_b64}${digest_b64}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(expected, actual)


# Verified against when an email is unknown, so a login miss costs the same
# time as a wrong password and doesn't reveal which emails are registered.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_credentials(email: str, password: str) -> str | None:
    """Returns a user-safe problem description, or None when acceptable."""
    if not _EMAIL_PATTERN.match(email):
        return "Enter a valid email address."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use a password of at least {MIN_PASSWORD_LENGTH} characters."
    return None


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.execute(
        select(User).where(User.email == normalize_email(email))
    ).scalar_one_or_none()


def create_user(
    session: Session, *, email: str, password: str, display_name: str = ""
) -> User:
    user = User(
        email=normalize_email(email),
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        is_guest=False,
    )
    session.add(user)
    session.flush()
    return user


def create_guest(session: Session) -> User:
    user = User(email=None, password_hash="", display_name="Guest", is_guest=True)
    session.add(user)
    session.flush()
    return user


def upgrade_guest(
    session: Session, user: User, *, email: str, password: str, display_name: str = ""
) -> User:
    """Turns a guest into a registered account in place, so every record the
    guest already created stays with them."""
    user.email = normalize_email(email)
    user.password_hash = hash_password(password)
    user.display_name = display_name.strip()
    user.is_guest = False
    session.flush()
    return user


def authenticate(session: Session, *, email: str, password: str) -> User | None:
    user = get_user_by_email(session, email)
    if user is None or not user.password_hash:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.password_hash) else None


def issue_session(session: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    days = GUEST_SESSION_DAYS if user.is_guest else SESSION_DAYS
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=_utcnow() + timedelta(days=days),
        )
    )
    session.flush()
    return token


def resolve_token(session: Session, token: str) -> User | None:
    if not token:
        return None
    row = session.execute(
        select(AuthSession).where(AuthSession.token_hash == token_hash(token))
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    if _as_aware(row.expires_at) <= _utcnow():
        return None
    return session.get(User, row.user_id)


def revoke_token(session: Session, token: str) -> bool:
    row = session.execute(
        select(AuthSession).where(AuthSession.token_hash == token_hash(token))
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = _utcnow()
    session.flush()
    return True


def serialize_user(user: User) -> dict[str, object]:
    return {
        "user_id": user.id,
        "email": user.email or "",
        "display_name": user.display_name,
        "is_guest": user.is_guest,
    }
