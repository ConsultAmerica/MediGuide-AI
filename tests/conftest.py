from __future__ import annotations

import pytest


@pytest.fixture()
def db_session(monkeypatch, tmp_path):
    """Points src.database.session at an isolated, throwaway sqlite file so
    tests never touch data/mediguide.db, and resets the cached engine/
    sessionmaker singletons that module keeps at import time."""
    import src.database.session as session_module

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(session_module, "DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(session_module, "_engine", None)
    monkeypatch.setattr(session_module, "_SessionLocal", None)

    session_module.init_db()

    yield session_module

    if session_module._engine is not None:
        session_module._engine.dispose()


@pytest.fixture()
def api_client(monkeypatch, tmp_path):
    """A TestClient wired to an isolated sqlite DB and isolated temp-file
    directories for document/imaging processing, so integration tests never
    touch data/mediguide.db or outputs/*."""
    import src.database.session as session_module
    import src.document_intelligence as document_intelligence_module
    import src.imaging as imaging_module
    import src.medication_workspace as medication_workspace_module

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(session_module, "DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(session_module, "_engine", None)
    monkeypatch.setattr(session_module, "_SessionLocal", None)
    monkeypatch.setattr(document_intelligence_module, "TEMP_DIR", tmp_path / "document_intelligence")
    monkeypatch.setattr(imaging_module, "TEMP_DIR", tmp_path / "imaging")
    monkeypatch.setattr(medication_workspace_module, "TEMP_DIR", tmp_path / "medication_workspace")

    from fastapi.testclient import TestClient

    import api

    with TestClient(api.app, raise_server_exceptions=False) as client:
        # Signed in as a fresh guest by default, since every record API now
        # requires an owner. Tests that need a second, separate owner use
        # the `other_user_headers` fixture.
        token = client.post("/api/auth/guest").json()["token"]
        client.headers["Authorization"] = f"Bearer {token}"
        yield client

    if session_module._engine is not None:
        session_module._engine.dispose()


@pytest.fixture()
def other_user_headers(api_client):
    """Authorization headers for a second, unrelated user — pass as
    ``headers=`` on a request to act as someone who owns none of the
    default client's records."""
    response = api_client.post("/api/auth/guest", headers={"Authorization": ""})
    return {"Authorization": f"Bearer {response.json()['token']}"}
