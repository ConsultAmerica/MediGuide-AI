from __future__ import annotations

import pymupdf

from tests.helpers import current_user_id, save_owned_medication_session


def _make_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


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


def test_search_below_min_length_returns_422(api_client):
    response = api_client.get("/api/search", params={"q": "a"})
    assert response.status_code == 422


def test_search_finds_confirmed_medication(api_client):
    _confirm_medication(api_client, "med-1", "Amoxicillin")

    response = api_client.get("/api/search", params={"q": "amoxi"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["type"] == "medication"
    assert results[0]["verification_status"] == "verified"
    assert results[0]["route"] == "/workspace/timeline"


def _upsert_lab_document(
    document_id: str, filename: str, field_label: str, *, owner_id: str
) -> None:
    import src.database.repository as repository_module
    from src.database.session import session_scope

    field = {
        "field_id": f"field-{document_id}",
        "label": field_label,
        "value": "6.7",
        "unit": "%",
        "reference_range": "",
        "status": "unknown",
        "confidence": "clearly_visible",
        "page_number": 1,
        "source_text": f"{field_label} 6.7%",
    }
    with session_scope() as session:
        repository_module.upsert_confirmed_document(
            session,
            document_id=document_id,
            filename=filename,
            page_count=1,
            pages=[{"page_number": 1, "preview_url": "", "text_available": True}],
            fields=[field],
            owner_id=owner_id,
        )


def test_search_finds_confirmed_document_via_lab_report_title(api_client):
    """Documents with lab observations surface as "Lab Report" entries (the
    timeline's own dedup rule) — search inherits that, it does not show a
    second, separate generic-document hit for the same PDF."""
    _upsert_lab_document(
        "doc-1", "a1c_report.pdf", "Hemoglobin A1C", owner_id=current_user_id(api_client)
    )

    response = api_client.get("/api/search", params={"q": "a1c"})
    assert response.status_code == 200
    results = response.json()["results"]
    lab_results = [r for r in results if r["type"] == "laboratory"]
    assert len(lab_results) == 1
    assert lab_results[0]["document_id"] == "doc-1"
    assert all(r["type"] != "document" for r in results)


def test_search_finds_lab_observation_by_alias(api_client):
    """"a1c" should find a LabObservation whose test_name is "Hemoglobin
    A1C" even though "a1c" is not literally a substring of that name,
    exercising the normalize_test_name()-based alias matching."""
    _upsert_lab_document("doc-1", "labs.pdf", "HbA1c", owner_id=current_user_id(api_client))

    response = api_client.get("/api/search", params={"q": "a1c"})
    assert response.status_code == 200
    titles = [r["title"] for r in response.json()["results"]]
    assert "Lab Report" in titles


def test_search_excludes_unconfirmed_document(api_client):
    from src.database.models import Document
    from src.database.session import session_scope

    with session_scope() as session:
        session.add(Document(id="doc-1", filename="draft_referral.pdf", confirmed=False))

    response = api_client.get("/api/search", params={"q": "referral"})
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_search_excludes_unverified_imaging_study(api_client):
    study = api_client.post(
        "/api/imaging/studies",
        json={"modality": "mri", "body_region": "Right knee", "study_date": "2026-09-02"},
    ).json()
    pdf_bytes = _make_pdf("EXAM: MRI Right Knee\nFINDINGS: No acute fracture.\n")
    api_client.post(
        f"/api/imaging/studies/{study['study_id']}/report",
        files={"file": ("r.pdf", pdf_bytes, "application/pdf")},
    )
    # Deliberately not confirmed.

    response = api_client.get("/api/search", params={"q": "knee"})
    assert response.status_code == 200
    assert all(r["type"] != "imaging" for r in response.json()["results"])


def test_search_finds_confirmed_imaging_report_section_excludes_unverified_one(api_client):
    study = api_client.post(
        "/api/imaging/studies",
        json={"modality": "mri", "body_region": "Right knee", "study_date": "2026-09-02"},
    ).json()
    pdf_bytes = _make_pdf(
        "EXAM: MRI Right Knee\nFINDINGS: Small joint effusion.\nIMPRESSION: Small joint effusion.\n"
    )
    api_client.post(
        f"/api/imaging/studies/{study['study_id']}/report",
        files={"file": ("r.pdf", pdf_bytes, "application/pdf")},
    )
    sections = api_client.get(f"/api/imaging/studies/{study['study_id']}/report/sections").json()["sections"]
    assert any(s["section_type"] == "findings" for s in sections)

    # Confirm only the findings section, leave impression (and any other
    # section) unverified, to prove search only surfaces the confirmed one.
    api_client.post(
        f"/api/imaging/studies/{study['study_id']}/report/confirm",
        json={"reviewed": True, "sections": [], "confirm_types": ["findings"]},
    )

    response = api_client.get("/api/search", params={"q": "effusion"})
    assert response.status_code == 200
    section_results = [r for r in response.json()["results"] if r["type"] == "imaging_section"]
    assert len(section_results) == 1
    assert "Findings" in section_results[0]["title"]


def test_search_does_not_duplicate_imaging_report_document(api_client):
    """The document backing a verified imaging study must appear once, as
    the imaging result — never a second time as a bare document result,
    mirroring the timeline's own dedup guarantee (run_search reuses
    get_timeline_entries for exactly this reason)."""
    study = api_client.post(
        "/api/imaging/studies",
        json={"modality": "mri", "body_region": "Right knee", "study_date": "2026-09-02"},
    ).json()
    pdf_bytes = _make_pdf("EXAM: MRI Right Knee shared_needle_xyz\nFINDINGS: No acute fracture.\n")
    api_client.post(
        f"/api/imaging/studies/{study['study_id']}/report",
        files={"file": ("shared_needle_xyz.pdf", pdf_bytes, "application/pdf")},
    )
    api_client.post(
        f"/api/imaging/studies/{study['study_id']}/report/confirm",
        json={"reviewed": True, "sections": []},
    )

    response = api_client.get("/api/search", params={"q": "shared_needle_xyz"})
    assert response.status_code == 200
    results = response.json()["results"]
    document_type_hits = [r for r in results if r["type"] == "document"]
    assert document_type_hits == []


def test_search_respects_per_type_cap(api_client):
    from src.search import PER_TYPE_CAP

    for i in range(PER_TYPE_CAP + 3):
        _confirm_medication(api_client, f"med-{i}", f"Capsulin Variant {i}")

    response = api_client.get("/api/search", params={"q": "capsulin"})
    assert response.status_code == 200
    medication_hits = [r for r in response.json()["results"] if r["type"] == "medication"]
    assert len(medication_hits) == PER_TYPE_CAP
