"""Durable record folders for serverless hosting (src/shared/file_store.py).

On a serverless host each request may run on a fresh instance with an empty
filesystem. These tests stand in a fake Blob store and wipe every local
record folder between requests: everything a reviewer needs (the original,
page previews, the review draft, imaging lines, medication sessions) must
come back from the store alone.
"""

from __future__ import annotations

import itertools
import shutil

import pytest

from src.shared import file_store
from tests.test_imaging_report_traceability import PAGE_ONE, PAGE_TWO, _pdf, _study, _upload
from tests.test_review_workflow import _lab_pdf


class FakeBlobStore:
    def __init__(self) -> None:
        self.blobs: dict[str, tuple[bytes, float]] = {}
        self._clock = itertools.count(1)
        self.fail_puts = False

    def list(self, prefix):
        return [(name, uploaded) for name, (_, uploaded) in self.blobs.items() if name.startswith(prefix)]

    def get(self, pathname):
        return self.blobs[pathname][0]

    def put(self, pathname, data):
        if self.fail_puts:
            raise RuntimeError("store unavailable")
        self.blobs[pathname] = (bytes(data), float(next(self._clock)))

    def delete(self, pathnames):
        for name in pathnames:
            self.blobs.pop(name, None)

    def under(self, prefix):
        return sorted(name for name in self.blobs if name.startswith(prefix))


@pytest.fixture()
def store(api_client):
    fake = FakeBlobStore()
    file_store.set_backend(fake)
    yield fake
    file_store.set_backend(None)


@pytest.fixture()
def fresh_instance(tmp_path):
    """Wipe every local record folder, as if the next request landed on an
    instance that has never seen them."""

    def wipe():
        for name in ("document_intelligence", "imaging", "medication_workspace"):
            shutil.rmtree(tmp_path / name, ignore_errors=True)

    return wipe


def test_a_document_review_survives_moving_between_instances(api_client, store, fresh_instance):
    uploaded = api_client.post("/api/documents/v2/upload", files={"file": ("labs.pdf", _lab_pdf(), "application/pdf")}).json()
    document_id = uploaded["document_id"]

    fresh_instance()
    state = api_client.post(f"/api/documents/v2/{document_id}/process").json()
    assert {field["label"] for field in state["fields"]} >= {"Glucose", "Sodium"}

    fresh_instance()
    preview = api_client.get(f"/api/documents/v2/{document_id}/pages/1/preview")
    assert preview.status_code == 200 and preview.content[:4] == b"\x89PNG"

    field_id = state["fields"][0]["field_id"]
    api_client.put(f"/api/documents/v2/{document_id}/review-draft", json={"items": {field_id: {"state": "confirmed"}}})
    fresh_instance()
    reopened = api_client.get(f"/api/documents/v2/{document_id}").json()
    assert reopened["review_draft"][field_id]["state"] == "confirmed"

    fresh_instance()
    confirmed = api_client.post(
        f"/api/documents/v2/{document_id}/confirm",
        json={"fields": reopened["fields"], "reviewed_names_values_units_dates": True},
    )
    assert confirmed.status_code == 200, confirmed.text
    fresh_instance()
    listed = api_client.get("/api/documents/v2/sessions").json()
    assert any(item["document_id"] == document_id and item["confirmed"] for item in listed["sessions"])


def test_each_file_is_kept_once_under_a_content_hashed_name(api_client, store):
    uploaded = api_client.post("/api/documents/v2/upload", files={"file": ("labs.pdf", _lab_pdf(), "application/pdf")}).json()
    document_id = uploaded["document_id"]
    api_client.post(f"/api/documents/v2/{document_id}/process")  # rewrites state.json

    names = [name.removeprefix(f"documents/{document_id}/") for name in store.under(f"documents/{document_id}/")]
    files = [name.rsplit("~", 1)[0] for name in names]
    assert "document.pdf" in files and "state.json" in files
    assert len(files) == len(set(files)), "an old version was left behind"
    assert all("~" in name for name in names)


def test_deleting_a_document_removes_its_stored_files(api_client, store, fresh_instance):
    uploaded = api_client.post("/api/documents/v2/upload", files={"file": ("labs.pdf", _lab_pdf(), "application/pdf")}).json()
    document_id = uploaded["document_id"]
    api_client.post(f"/api/documents/v2/{document_id}/process")
    assert store.under(f"documents/{document_id}/")

    fresh_instance()
    assert api_client.delete(f"/api/documents/v2/{document_id}").status_code == 200
    assert store.under(f"documents/{document_id}/") == []


def test_an_imaging_report_keeps_its_pages_and_lines_across_instances(api_client, store, fresh_instance):
    study_id = _study(api_client)
    _upload(api_client, study_id, _pdf([PAGE_ONE, PAGE_TWO]))

    fresh_instance()
    assert api_client.get(f"/api/imaging/studies/{study_id}/report/pages/2/preview").status_code == 200
    fresh_instance()
    lines = api_client.get(f"/api/imaging/studies/{study_id}/report/lines").json()
    assert lines["adjustable"] and any("IMPRESSION" in line["text"] for line in lines["lines"])


def test_a_medication_session_and_its_owner_survive_across_instances(api_client, store, fresh_instance, other_user_headers):
    created = api_client.post("/api/medications/v2/text", json={"text": "Amoxicillin 500 mg capsules. Take 1 capsule by mouth three times daily."})
    assert created.status_code == 200, created.text
    medication_id = created.json()["medication_id"]

    fresh_instance()
    assert api_client.get(f"/api/medications/v2/{medication_id}").status_code == 200
    fresh_instance()
    assert api_client.get(f"/api/medications/v2/{medication_id}", headers=other_user_headers).status_code == 404


def test_a_failed_save_is_reported_instead_of_claiming_success(api_client, store):
    store.fail_puts = True
    response = api_client.post("/api/documents/v2/upload", files={"file": ("labs.pdf", _lab_pdf(), "application/pdf")})
    assert response.status_code == 503
    assert "couldn't be saved" in response.json()["detail"]


def test_without_durable_storage_folders_are_plain_paths(tmp_path, monkeypatch):
    monkeypatch.delenv("MEDIGUIDE_FILE_STORE", raising=False)
    file_store.set_backend(None)
    assert not file_store.enabled()
    assert file_store.folder("documents", tmp_path, "abc") == tmp_path / "abc"
    assert file_store.begin_request() is None
