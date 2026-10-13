"""Shared helpers for tests that seed records directly instead of through
the API, and so must attach the same owner the API client is signed in as."""

from __future__ import annotations


def current_user_id(client) -> str:
    return client.get("/api/auth/me").json()["user"]["user_id"]


def save_owned_medication_session(client, state) -> None:
    import src.medication_workspace as medication_workspace_module

    medication_workspace_module._save_state(state)
    medication_workspace_module._owner_path(state.medication_id).write_text(
        current_user_id(client), encoding="utf-8"
    )
