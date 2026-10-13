from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

ANON = {"Authorization": ""}
PASSWORD = "correct horse battery"


def _register(client, email="pat@example.com", password=PASSWORD, headers=ANON):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "Pat"},
        headers=headers,
    )


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_record_api_without_a_session_is_401(api_client):
    response = api_client.get("/api/timeline", headers=ANON)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_unknown_token_is_401_session_expired(api_client):
    response = api_client.get("/api/timeline", headers=_bearer("not-a-real-token"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"


def test_register_then_login_then_me(api_client):
    registered = _register(api_client)
    assert registered.status_code == 200
    assert registered.json()["user"]["email"] == "pat@example.com"
    assert registered.json()["user"]["is_guest"] is False

    login = api_client.post(
        "/api/auth/login",
        json={"email": "PAT@example.com ", "password": PASSWORD},
        headers=ANON,
    )
    assert login.status_code == 200
    me = api_client.get("/api/auth/me", headers=_bearer(login.json()["token"]))
    assert me.json()["user"]["email"] == "pat@example.com"


def test_wrong_password_and_unknown_email_get_the_same_error(api_client):
    _register(api_client)
    wrong = api_client.post(
        "/api/auth/login", json={"email": "pat@example.com", "password": "nope-nope-nope"}, headers=ANON
    )
    unknown = api_client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}, headers=ANON
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_duplicate_email_is_409(api_client):
    _register(api_client)
    assert _register(api_client).status_code == 409


def test_short_password_and_bad_email_are_422(api_client):
    assert _register(api_client, password="short").status_code == 422
    assert _register(api_client, email="not-an-email").status_code == 422


def test_logout_revokes_the_token(api_client):
    token = _register(api_client).json()["token"]
    assert api_client.post("/api/auth/logout", headers=_bearer(token)).status_code == 200
    assert api_client.get("/api/auth/me", headers=_bearer(token)).status_code == 401


def test_expired_session_is_rejected(api_client):
    from src.auth.service import token_hash
    from src.database.models import AuthSession
    from src.database.session import session_scope

    token = _register(api_client).json()["token"]
    with session_scope() as session:
        row = session.execute(
            select(AuthSession).where(AuthSession.token_hash == token_hash(token))
        ).scalar_one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    assert api_client.get("/api/auth/me", headers=_bearer(token)).status_code == 401


def test_credentials_are_never_stored_in_plain_text(api_client):
    from src.database.models import AuthSession, User
    from src.database.session import session_scope

    token = _register(api_client).json()["token"]
    with session_scope() as session:
        user = session.execute(select(User).where(User.email == "pat@example.com")).scalar_one()
        assert PASSWORD not in user.password_hash
        assert user.password_hash.startswith("scrypt$")
        stored = session.execute(select(AuthSession.token_hash)).scalars().all()
        assert token not in stored


def test_registering_from_a_guest_workspace_keeps_its_records(api_client):
    """The default api_client is a guest; registering with its token must
    upgrade that same account so its imaging study stays visible."""
    study = api_client.post("/api/imaging/studies", json={"modality": "mri"}).json()
    guest_token = api_client.headers["Authorization"].split(" ", 1)[1]

    registered = _register(api_client, headers=_bearer(guest_token))
    assert registered.status_code == 200
    new_token = registered.json()["token"]

    # The guest token is retired; the new one sees the guest's record.
    assert api_client.get("/api/auth/me", headers=_bearer(guest_token)).status_code == 401
    studies = api_client.get("/api/imaging/studies", headers=_bearer(new_token)).json()["studies"]
    assert [s["study_id"] for s in studies] == [study["study_id"]]
