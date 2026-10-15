"""Verification workflow (Stage F3.3): resumable reviews and the audit trail.

A partially completed review is saved server-side and restored when the
document is reopened; confirmed fields keep the printed flag, the source
region, what extraction originally read, the reviewer's decision and when
it was made.
"""

from __future__ import annotations

import json
import sqlite3

import pymupdf

COLUMNS = (72, 230, 290, 330, 440)


def _lab_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Laboratory Results", fontsize=14)
    page.insert_text((72, 82), "Collected: 03/15/2026", fontsize=10)
    for x, text in zip(COLUMNS, ("Test", "Result", "Flag", "Reference Range", "Units")):
        page.insert_text((x, 110), text, fontsize=10)
    for i, row in enumerate([("Glucose", "112", "H", "70 - 99", "mg/dL"), ("Sodium", "139", "", "136 - 145", "mmol/L")]):
        for x, text in zip(COLUMNS, row):
            if text:
                page.insert_text((x, 130 + i * 18), text, fontsize=10)
    return doc.tobytes()


def _processed(client) -> dict:
    uploaded = client.post("/api/documents/v2/upload", files={"file": ("labs.pdf", _lab_pdf(), "application/pdf")}).json()
    return client.post(f"/api/documents/v2/{uploaded['document_id']}/process").json()


def _field(state, label):
    return next(f for f in state["fields"] if f["label"] == label)


def test_partial_review_is_saved_and_restored_when_the_document_is_reopened(api_client):
    state = _processed(api_client)
    glucose, sodium = _field(state, "Glucose"), _field(state, "Sodium")
    draft = {
        glucose["field_id"]: {"state": "corrected", "value": "113"},
        sodium["field_id"]: {"state": "confirmed"},
    }
    saved = api_client.put(f"/api/documents/v2/{state['document_id']}/review-draft", json={"items": draft})
    assert saved.status_code == 200
    assert saved.json()["reviewed"] == 2 and saved.json()["total"] == len(state["fields"])

    reopened = api_client.get(f"/api/documents/v2/{state['document_id']}").json()
    assert reopened["review_draft"][glucose["field_id"]] == {"state": "corrected", "label": None, "value": "113", "unit": None, "reference_range": None}
    assert reopened["review_draft"][sodium["field_id"]]["state"] == "confirmed"
    assert reopened["review_draft_saved_at"]
    # The extraction itself is untouched by a draft.
    assert _field(reopened, "Glucose")["value"] == "112"


def test_rereading_the_document_discards_the_old_draft(api_client):
    state = _processed(api_client)
    field_id = state["fields"][0]["field_id"]
    api_client.put(f"/api/documents/v2/{state['document_id']}/review-draft",
                   json={"items": {field_id: {"state": "rejected"}}})

    reread = api_client.post(f"/api/documents/v2/{state['document_id']}/reextract")
    assert reread.status_code == 200
    assert reread.json()["review_draft"] == {}
    assert api_client.get(f"/api/documents/v2/{state['document_id']}").json()["review_draft"] == {}


def test_confirming_clears_the_draft(api_client):
    state = _processed(api_client)
    field_id = state["fields"][0]["field_id"]
    api_client.put(f"/api/documents/v2/{state['document_id']}/review-draft",
                   json={"items": {field_id: {"state": "confirmed"}}})
    api_client.post(f"/api/documents/v2/{state['document_id']}/confirm",
                    json={"fields": state["fields"], "reviewed_names_values_units_dates": True})
    assert api_client.get(f"/api/documents/v2/{state['document_id']}").json()["review_draft"] == {}


def test_draft_with_an_unknown_field_is_refused(api_client):
    state = _processed(api_client)
    response = api_client.put(f"/api/documents/v2/{state['document_id']}/review-draft",
                              json={"items": {"invented": {"state": "confirmed"}}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNKNOWN_FIELD"


def test_draft_on_a_confirmed_document_is_refused(api_client):
    state = _processed(api_client)
    api_client.post(f"/api/documents/v2/{state['document_id']}/confirm",
                    json={"fields": state["fields"], "reviewed_names_values_units_dates": True})
    response = api_client.put(f"/api/documents/v2/{state['document_id']}/review-draft", json={"items": {}})
    assert response.status_code == 409


def test_another_account_cannot_read_or_write_the_draft(api_client, other_user_headers):
    state = _processed(api_client)
    field_id = state["fields"][0]["field_id"]
    api_client.put(f"/api/documents/v2/{state['document_id']}/review-draft",
                   json={"items": {field_id: {"state": "confirmed"}}})

    written = api_client.put(f"/api/documents/v2/{state['document_id']}/review-draft",
                             json={"items": {field_id: {"state": "rejected"}}}, headers=other_user_headers)
    assert written.status_code == 404
    assert api_client.get(f"/api/documents/v2/{state['document_id']}", headers=other_user_headers).status_code == 404
    mine = api_client.get(f"/api/documents/v2/{state['document_id']}").json()
    assert mine["review_draft"][field_id]["state"] == "confirmed"


def test_confirmed_fields_keep_flag_region_original_reading_and_decision(api_client, tmp_path):
    state = _processed(api_client)
    edited = [{**f, "value": "113"} if f["label"] == "Glucose" else f for f in state["fields"]]
    response = api_client.post(f"/api/documents/v2/{state['document_id']}/confirm",
                               json={"fields": edited, "reviewed_names_values_units_dates": True})
    assert response.status_code == 200

    from src.database.models import ExtractedField
    from src.database.session import session_scope

    with session_scope() as session:
        rows = {row.label: row for row in session.query(ExtractedField).filter_by(document_id=state["document_id"]).all()}
        glucose, sodium = rows["Glucose"], rows["Sodium"]
        assert glucose.value == "113" and glucose.review_status == "corrected"
        assert json.loads(glucose.extracted_snapshot)["value"] == "112"
        assert glucose.flag == "H"
        assert glucose.bbox_x is not None and glucose.bbox_width > 0 and glucose.bbox_height > 0
        assert glucose.reviewed_at is not None
        assert sodium.review_status == "confirmed" and sodium.flag == ""


def test_audit_columns_are_created_by_the_migration(tmp_path):
    from tests.test_migrations import _run_alembic

    db_path = tmp_path / "audit.db"
    _run_alembic("upgrade", "head", db_path=db_path)
    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(extracted_fields)")}
    assert {"flag", "extracted_snapshot", "review_status", "reviewed_at"} <= columns
