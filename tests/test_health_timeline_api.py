from __future__ import annotations

import pymupdf

from tests.helpers import save_owned_medication_session


def _make_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


def test_timeline_empty_by_default(api_client):
    response = api_client.get("/api/timeline")
    assert response.status_code == 200
    assert response.json() == {"entries": [], "next_cursor": None, "total_matched": 0}


def test_timeline_reflects_a_confirmed_imaging_study(api_client):
    study = api_client.post(
        "/api/imaging/studies",
        json={"modality": "mri", "body_region": "Right knee", "study_date": "2026-09-02"},
    ).json()
    pdf_bytes = _make_pdf("EXAM: MRI Right Knee\nFINDINGS: No acute fracture.\nIMPRESSION: No acute fracture.\n")
    api_client.post(
        f"/api/imaging/studies/{study['study_id']}/report",
        files={"file": ("r.pdf", pdf_bytes, "application/pdf")},
    )
    api_client.post(
        f"/api/imaging/studies/{study['study_id']}/report/confirm",
        json={"reviewed": True, "sections": []},
    )

    response = api_client.get("/api/timeline")
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["category"] == "imaging"
    assert entries[0]["link"] == {"type": "imaging_study", "id": study["study_id"]}


def test_timeline_omits_an_unconfirmed_imaging_study(api_client):
    study = api_client.post("/api/imaging/studies", json={"modality": "ct"}).json()
    pdf_bytes = _make_pdf("EXAM: CT Chest\nFINDINGS: No acute findings.\n")
    api_client.post(
        f"/api/imaging/studies/{study['study_id']}/report",
        files={"file": ("r.pdf", pdf_bytes, "application/pdf")},
    )
    # Deliberately not confirmed.

    response = api_client.get("/api/timeline")
    assert response.json()["entries"] == []


def test_medication_persists_on_confirm_and_appears_in_timeline(api_client):
    # 404 before any confirm has happened.
    missing = api_client.get("/api/medications/v2/never-confirmed/record")
    assert missing.status_code == 404

    # Seeds a reviewable session directly rather than going through the
    # AI-based /text extraction endpoint, which calls a live Ollama text
    # model and is not something an integration test should depend on —
    # confirm() itself (what this test actually exercises) makes no AI
    # calls at all.
    import src.medication_workspace as medication_workspace_module

    medication_id = "test-med-1"
    fields = [
        {"key": "medication_name", "label": "Medication name", "value": "Amoxicillin", "confidence": "clearly_visible"},
        {"key": "strength", "label": "Strength", "value": "500mg", "confidence": "clearly_visible"},
        {"key": "instructions", "label": "Directions for use", "value": "Take one three times daily.", "confidence": "clearly_visible"},
    ]
    state = medication_workspace_module.MedicationState(
        medication_id=medication_id,
        source="typed",
        status="review_required",
        fields=[medication_workspace_module.MedicationField(**f) for f in fields],
        confirmed=False,
    )
    save_owned_medication_session(api_client, state)

    # Not yet confirmed — no record persisted.
    before_confirm = api_client.get(f"/api/medications/v2/{medication_id}/record")
    assert before_confirm.status_code == 404

    confirm = api_client.post(
        f"/api/medications/v2/{medication_id}/confirm",
        json={"fields": fields, "reviewed_name_strength_instructions": True},
    )
    assert confirm.status_code == 200

    record = api_client.get(f"/api/medications/v2/{medication_id}/record")
    assert record.status_code == 200
    assert record.json()["medication_id"] == medication_id

    timeline = api_client.get("/api/timeline").json()["entries"]
    medication_entries = [e for e in timeline if e["category"] == "medication"]
    assert len(medication_entries) == 1
    assert medication_entries[0]["link"] == {"type": "medication", "id": medication_id}


def test_health_isolates_timeline_from_core(api_client, monkeypatch):
    import api as api_module

    monkeypatch.setattr(api_module, "probe_timeline", lambda: (False, "simulated outage"))
    response = api_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["statuses"]["timeline"]["status"] == "unavailable"
    assert body["status"] == "ok"


# --------------------------------------------------------------------------
# Phase 2: filters, pagination
# --------------------------------------------------------------------------


def _confirm_medication(api_client, medication_id: str, name: str) -> None:
    import src.medication_workspace as medication_workspace_module

    fields = [
        {"key": "medication_name", "label": "Medication name", "value": name, "confidence": "clearly_visible"},
    ]
    state = medication_workspace_module.MedicationState(
        medication_id=medication_id,
        source="typed",
        status="review_required",
        fields=[medication_workspace_module.MedicationField(**f) for f in fields],
        confirmed=False,
    )
    save_owned_medication_session(api_client, state)
    response = api_client.post(
        f"/api/medications/v2/{medication_id}/confirm",
        json={"fields": fields, "reviewed_name_strength_instructions": True},
    )
    assert response.status_code == 200


def test_timeline_endpoint_accepts_type_date_search_params(api_client):
    _confirm_medication(api_client, "med-1", "Amoxicillin")
    _confirm_medication(api_client, "med-2", "Lisinopril")

    by_type = api_client.get("/api/timeline", params={"event_type": "medication"}).json()
    assert all(entry["category"] == "medication" for entry in by_type["entries"])

    by_search = api_client.get("/api/timeline", params={"search": "amoxicillin"}).json()
    assert len(by_search["entries"]) == 1
    assert by_search["entries"][0]["subtitle"] == "Amoxicillin"

    no_match = api_client.get("/api/timeline", params={"search": "ibuprofen"}).json()
    assert no_match["entries"] == []


def test_timeline_endpoint_limit_bounds(api_client):
    assert api_client.get("/api/timeline", params={"limit": 0}).status_code == 422
    assert api_client.get("/api/timeline", params={"limit": 101}).status_code == 422
    assert api_client.get("/api/timeline", params={"limit": 100}).status_code == 200


def test_timeline_endpoint_cursor_round_trip(api_client):
    _confirm_medication(api_client, "med-1", "Amoxicillin")
    _confirm_medication(api_client, "med-2", "Lisinopril")

    page_one = api_client.get("/api/timeline", params={"limit": 1}).json()
    assert len(page_one["entries"]) == 1
    assert page_one["next_cursor"] is not None

    page_two = api_client.get(
        "/api/timeline", params={"limit": 1, "cursor": page_one["next_cursor"]}
    ).json()
    assert len(page_two["entries"]) == 1
    assert page_two["entries"][0]["entry_id"] != page_one["entries"][0]["entry_id"]
    # Back-compat: the envelope's `entries` key is still present and shaped
    # the same as before pagination existed.
    assert isinstance(page_two["entries"], list)


def test_recent_history_limit_5_matches_full_timeline_prefix(api_client):
    for i in range(7):
        _confirm_medication(api_client, f"med-{i}", f"Medication {i}")

    full = api_client.get("/api/timeline").json()["entries"]
    limited = api_client.get("/api/timeline", params={"limit": 5}).json()["entries"]

    assert len(limited) == 5
    assert [e["entry_id"] for e in limited] == [e["entry_id"] for e in full[:5]]
