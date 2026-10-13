from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from src.auth.dependencies import bearer_token, require_user
from src.auth.service import (
    authenticate,
    create_guest,
    create_user,
    get_user_by_email,
    issue_session,
    normalize_email,
    resolve_token,
    revoke_token,
    serialize_user,
    upgrade_guest,
    validate_credentials,
)
from src.database.models import User
from src.database.session import session_scope
from src.observability.logging import get_logger
from src.shared.errors import MediGuideError

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)
    display_name: str = Field(default="", max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


def _session_payload(token: str, user: User) -> dict[str, object]:
    return {"token": token, "user": serialize_user(user)}


@router.post("/register")
def register(request: RegisterRequest, http_request: Request) -> dict[str, object]:
    email = normalize_email(request.email)
    problem = validate_credentials(email, request.password)
    if problem:
        raise MediGuideError("INVALID_CREDENTIALS_FORMAT", problem, status_code=422)

    with session_scope() as session:
        if get_user_by_email(session, email) is not None:
            raise MediGuideError(
                "EMAIL_ALREADY_REGISTERED",
                "An account with this email already exists. Sign in instead.",
                status_code=409,
            )
        # Registering from inside a guest workspace keeps that workspace's
        # records: the guest is upgraded in place rather than abandoned.
        current = resolve_token(session, bearer_token(http_request))
        if current is not None and current.is_guest:
            user = upgrade_guest(
                session,
                current,
                email=email,
                password=request.password,
                display_name=request.display_name,
            )
            revoke_token(session, bearer_token(http_request))
        else:
            user = create_user(
                session,
                email=email,
                password=request.password,
                display_name=request.display_name,
            )
        token = issue_session(session, user)
        logger.info("account_registered", extra={"user_id": user.id})
        return _session_payload(token, user)


@router.post("/login")
def login(request: LoginRequest) -> dict[str, object]:
    with session_scope() as session:
        user = authenticate(session, email=request.email, password=request.password)
        if user is None:
            logger.info("login_failed")
            raise MediGuideError(
                "INVALID_CREDENTIALS",
                "That email and password don't match an account.",
                status_code=401,
            )
        token = issue_session(session, user)
        logger.info("login_succeeded", extra={"user_id": user.id})
        return _session_payload(token, user)


@router.post("/guest")
def guest() -> dict[str, object]:
    with session_scope() as session:
        user = create_guest(session)
        token = issue_session(session, user)
        logger.info("guest_workspace_created", extra={"user_id": user.id})
        return _session_payload(token, user)


@router.post("/logout")
def logout(http_request: Request, user: User = Depends(require_user)) -> dict[str, object]:
    with session_scope() as session:
        revoke_token(session, bearer_token(http_request))
    return {"signed_out": True}


@router.get("/me")
def me(user: User = Depends(require_user)) -> dict[str, object]:
    return {"user": serialize_user(user)}
