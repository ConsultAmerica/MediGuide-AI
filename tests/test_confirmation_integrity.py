"""Confirmation can only ever record what was extracted plus the reviewer's
own text edits; it is all-or-nothing; and once confirmed, a record is not
silently overwritten. Original uploads stay on disk until their owner
deletes them.
"""

from __future__ import annotations

import os
import time

import pymupdf

LAB_TEXT = (
    "Report date: 2026-09-01\n"
    "Hemoglobin A1C 6.7 % Ref 4.0-5.6\n"
    "Glucose 98 mg/dL Ref 70-99\n"
)
IMAGING_TEXT = "EXAM: MRI Right Knee\nFINDINGS: Small joint effusion.\nIMPRESSION: Small joint effusion.\n"


def _pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def _processed(client, text: str = LAB_TEXT) -> tuple[str, list[dict]]:
    uploaded = client.post(
        "/api/documents/v2/upload", files={"file": ("labs.pdf", _pdf(text), "application/pdf")}
    ).json()
    state = client.post(f"/api/documents/v2/{uploaded['document_id']}/process").json()
    assert state["status"] == "review_required"
    return uploaded["document_id"], state["fields"]


def _confirm(client, document_id, fields, **extra):
    return client.post(
        f"/api/documents/v2/{document_id}/confirm",
        json={"fields": fields, "reviewed_names_values_units_dates": True, **extra},
    )


def _field(fields, label_fragment):
    return next(f for f in fields if label_fragment.lower() in f["label"].lower())


def test_confirm_cannot_rewrite_provenance(api_client):
    document_id, fields = _processed(api_client)
    original = _field(fields, "a1c")
    forged = [
        {**f, "source_text": "FORGED", "page_number": 9, "confidence": "clearly_visible"}
        if f["field_id"] == original["field_id"]
        else f
        for f in fields
    ]

    response = _confirm(api_client, document_id, forged)
    assert response.status_code == 200
    saved = _field(response.json()["fields"], "a1c")
    assert saved["source_text"] == original["source_text"]
    assert saved["page_number"] == original["page_number"]
    assert saved["user_edited"] is False


def test_reviewer_edits_are_kept_and_flagged(api_client):
    document_id, fields = _processed(api_client)
    target = _field(fields, "a1c")
    edited = [{**f, "value": "6.9"} if f["field_id"] == target["field_id"] else f for f in fields]

    saved = _field(_confirm(api_client, document_id, edited).json()["fields"], "a1c")
    assert saved["value"] == "6.9"
    assert saved["user_edited"] is True
    point = api_client.get("/api/labs/timeline/hemoglobin_a1c").json()["points"][0]
    assert point["value"] == 6.9


def test_unknown_field_is_rejected_and_nothing_is_saved(api_client):
    document_id, fields = _processed(api_client)
    injected = [*fields, {**fields[0], "field_id": "invented", "label": "Hemoglobin A1C", "value": "12"}]

    response = _confirm(api_client, document_id, injected)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNKNOWN_FIELD"
    assert api_client.get(f"/api/documents/v2/{document_id}").json()["confirmed"] is False
    assert api_client.get("/api/labs/timeline/hemoglobin_a1c").json()["count"] == 0


def test_rejected_fields_never_become_lab_observations(api_client):
    document_id, fields = _processed(api_client)
    rejected = _field(fields, "a1c")["field_id"]

    response = _confirm(api_client, document_id, fields, excluded_field_ids=[rejected])
    assert response.status_code == 200
    assert all(f["field_id"] != rejected for f in response.json()["fields"])
    assert api_client.get("/api/labs/timeline/hemoglobin_a1c").json()["count"] == 0
    assert api_client.get("/api/labs/timeline/glucose").json()["count"] == 1


def test_rejecting_everything_is_refused(api_client):
    document_id, fields = _processed(api_client)
    response = _confirm(api_client, document_id, fields, excluded_field_ids=[f["field_id"] for f in fields])
    assert response.status_code == 400


def test_confirmed_document_is_not_overwritten(api_client):
    document_id, fields = _processed(api_client)
    assert _confirm(api_client, document_id, fields).status_code == 200

    target = _field(fields, "a1c")
    changed = [{**f, "value": "99"} if f["field_id"] == target["field_id"] else f for f in fields]
    again = _confirm(api_client, document_id, changed)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "DOCUMENT_ALREADY_CONFIRMED"
    point = api_client.get("/api/labs/timeline/hemoglobin_a1c").json()["points"][0]
    assert point["value"] == 6.7


def test_database_failure_during_confirm_leaves_the_review_unconfirmed(api_client, monkeypatch):
    import src.document_intelligence as document_intelligence

    def _boom(*args, **kwargs):
        raise RuntimeError("database went away")

    document_id, fields = _processed(api_client)
    real = document_intelligence.create_observations_from_document
    monkeypatch.setattr(document_intelligence, "create_observations_from_document", _boom)

    response = _confirm(api_client, document_id, fields)
    assert response.status_code == 503
    body = response.json()["error"]
    assert body["code"] == "CONFIRMATION_NOT_SAVED"
    assert body["retryable"] is True
    assert "database went away" not in body["message"]
    assert api_client.get(f"/api/documents/v2/{document_id}").json()["confirmed"] is False

    # Not monkeypatch.undo(): that would also revert api_client's isolated DB.
    monkeypatch.setattr(document_intelligence, "create_observations_from_document", real)
    assert _confirm(api_client, document_id, fields).status_code == 200


def test_confirm_before_processing_is_refused(api_client):
    uploaded = api_client.post(
        "/api/documents/v2/upload", files={"file": ("labs.pdf", _pdf(LAB_TEXT), "application/pdf")}
    ).json()
    response = _confirm(api_client, uploaded["document_id"], [])
    assert response.status_code == 409


def test_old_owned_uploads_survive_the_sweep_and_orphans_do_not(api_client):
    import src.document_intelligence as document_intelligence

    document_id, fields = _processed(api_client)
    _confirm(api_client, document_id, fields)
    owned_folder = document_intelligence._folder(document_id)
    orphan_folder = document_intelligence.TEMP_DIR / "orphan-upload"
    orphan_folder.mkdir(parents=True)

    long_ago = time.time() - 60 * 60 * 24 * 30
    for folder in (owned_folder, orphan_folder):
        os.utime(folder, (long_ago, long_ago))

    document_intelligence._cleanup_expired_sessions()

    assert owned_folder.exists()
    assert not orphan_folder.exists()
    preview = api_client.get(f"/api/documents/v2/{document_id}/pages/1/preview")
    assert preview.status_code == 200


def test_owner_can_delete_a_document_and_its_files(api_client):
    import src.document_intelligence as document_intelligence

    document_id, fields = _processed(api_client)
    _confirm(api_client, document_id, fields)

    assert api_client.delete(f"/api/documents/v2/{document_id}").status_code == 200
    assert not document_intelligence._folder(document_id).exists()
    assert api_client.get(f"/api/documents/v2/{document_id}").status_code == 404
    assert api_client.get("/api/labs/timeline/hemoglobin_a1c").json()["count"] == 0


def test_verified_imaging_study_refuses_a_replacement_report(api_client):
    study = api_client.post("/api/imaging/studies", json={"modality": "mri"}).json()
    study_id = study["study_id"]
    api_client.post(
        f"/api/imaging/studies/{study_id}/report",
        files={"file": ("r.pdf", _pdf(IMAGING_TEXT), "application/pdf")},
    )
    api_client.post(f"/api/imaging/studies/{study_id}/report/confirm", json={"reviewed": True, "sections": []})
    findings = api_client.get(f"/api/imaging/studies/{study_id}/findings").json()["findings"]
    api_client.post(
        f"/api/imaging/studies/{study_id}/findings/confirm",
        json={"reviewed": True, "findings": [{"finding_id": f["finding_id"], "verification_status": "confirmed"} for f in findings]},
    )

    replacement = api_client.post(
        f"/api/imaging/studies/{study_id}/report",
        files={"file": ("r2.pdf", _pdf("EXAM: CT\nIMPRESSION: Different text.\n"), "application/pdf")},
    )
    assert replacement.status_code == 409
    assert replacement.json()["error"]["code"] == "STUDY_ALREADY_VERIFIED"
    after = api_client.get(f"/api/imaging/studies/{study_id}/findings").json()["findings"]
    assert [f["finding_id"] for f in after] == [f["finding_id"] for f in findings]
    assert all(f["verification_status"] == "confirmed" for f in after)
