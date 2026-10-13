"""One user's records are invisible to every other user, on every record
API. Cross-owner access is always 404 (never 403), so ids can't be probed.
"""

from __future__ import annotations

import pymupdf
import pytest

from tests.helpers import save_owned_medication_session

LAB_TEXT = "Report date: 2026-09-01\nHemoglobin A1C 6.7 % Ref 4.0-5.6\n"
IMAGING_TEXT = (
    "EXAM: MRI Right Knee\n"
    "FINDINGS: Small joint effusion.\n"
    "IMPRESSION: Small joint effusion.\n"
)


def _pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def _confirmed_lab_document(client) -> dict:
    uploaded = client.post(
        "/api/documents/v2/upload", files={"file": ("labs.pdf", _pdf(LAB_TEXT), "application/pdf")}
    ).json()
    document_id = uploaded["document_id"]
    state = client.post(f"/api/documents/v2/{document_id}/process").json()
    confirmed = client.post(
        f"/api/documents/v2/{document_id}/confirm",
        json={"fields": state["fields"], "reviewed_names_values_units_dates": True},
    )
    assert confirmed.status_code == 200, confirmed.text
    return {"document_id": document_id, "state": state}


def _verified_study(client) -> dict:
    study = client.post(
        "/api/imaging/studies", json={"modality": "mri", "body_region": "Right knee"}
    ).json()
    report = client.post(
        f"/api/imaging/studies/{study['study_id']}/report",
        files={"file": ("report.pdf", _pdf(IMAGING_TEXT), "application/pdf")},
    ).json()
    client.post(
        f"/api/imaging/studies/{study['study_id']}/report/confirm",
        json={"reviewed": True, "sections": []},
    )
    return {"study_id": study["study_id"], "document_id": report["document_id"]}


# --------------------------------------------------------------------------
# Route guard: every route on a record router requires a signed-in user.
# --------------------------------------------------------------------------

# Public by design: synthetic sample files and static reference lists.
_PUBLIC_RECORD_ROUTER_PATHS = {
    "/api/documents/v2/sample/lab-report",
    "/api/imaging/samples",
    "/api/imaging/samples/{slug}",
}


def _record_routers():
    from src.api.labs import router as labs
    from src.document_intelligence import router as documents
    from src.health_timeline import router as timeline
    from src.imaging import router as imaging
    from src.medication_workspace import router as medications
    from src.search import router as search

    return [labs, documents, timeline, imaging, medications, search]


def test_every_record_route_requires_a_user():
    from fastapi.routing import APIRoute

    unguarded = []
    for router in _record_routers():
        for route in router.routes:
            if not isinstance(route, APIRoute) or route.path in _PUBLIC_RECORD_ROUTER_PATHS:
                continue
            names = {getattr(dep.call, "__name__", "") for dep in route.dependant.dependencies}
            if "require_user" not in names:
                unguarded.append(f"{sorted(route.methods)} {route.path}")
    assert unguarded == []


def test_direct_lab_write_route_is_gone(api_client):
    response = api_client.post("/api/labs/from-document/anything", json={"fields": [{}]})
    assert response.status_code in {404, 405}


# --------------------------------------------------------------------------
# Cross-owner isolation
# --------------------------------------------------------------------------


def test_documents_are_isolated(api_client, other_user_headers):
    owned = _confirmed_lab_document(api_client)
    document_id = owned["document_id"]
    other = other_user_headers

    for method, path in [
        ("get", f"/api/documents/v2/{document_id}"),
        ("get", f"/api/documents/v2/{document_id}/status"),
        ("get", f"/api/documents/v2/{document_id}/pages/1/preview"),
        ("post", f"/api/documents/v2/{document_id}/process"),
        ("delete", f"/api/documents/v2/{document_id}"),
    ]:
        response = getattr(api_client, method)(path, headers=other)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"

    confirm = api_client.post(
        f"/api/documents/v2/{document_id}/confirm",
        json={"fields": owned["state"]["fields"], "reviewed_names_values_units_dates": True},
        headers=other,
    )
    assert confirm.status_code == 404
    explain = api_client.post(f"/api/documents/v2/{document_id}/explain", json={}, headers=other)
    assert explain.status_code == 404

    assert api_client.get("/api/documents/v2/sessions", headers=other).json()["count"] == 0
    # The owner still has it, untouched by the attempts above.
    assert api_client.get("/api/documents/v2/sessions").json()["count"] == 1
    assert api_client.get(f"/api/documents/v2/{document_id}").json()["confirmed"] is True


def test_labs_are_isolated(api_client, other_user_headers):
    _confirmed_lab_document(api_client)
    points = api_client.get("/api/labs/timeline/hemoglobin_a1c").json()["points"]
    assert len(points) == 1
    observation_id = points[0]["observation_id"]
    other = other_user_headers

    assert api_client.get("/api/labs/timeline/hemoglobin_a1c", headers=other).json()["count"] == 0
    assert api_client.get("/api/labs/summary", headers=other).json()["count"] == 0
    tests = api_client.get("/api/labs/tests", headers=other).json()["tests"]
    assert all(test["observation_count"] == 0 for test in tests)
    assert api_client.get(f"/api/labs/observations/{observation_id}", headers=other).status_code == 404
    assert api_client.delete(f"/api/labs/observations/{observation_id}", headers=other).status_code == 404
    # Still there for the owner.
    assert api_client.get(f"/api/labs/observations/{observation_id}").status_code == 200


def test_imaging_is_isolated(api_client, other_user_headers):
    owned = _verified_study(api_client)
    study_id = owned["study_id"]
    other = other_user_headers

    for method, path in [
        ("get", f"/api/imaging/studies/{study_id}"),
        ("get", f"/api/imaging/studies/{study_id}/report/status"),
        ("get", f"/api/imaging/studies/{study_id}/report/sections"),
        ("get", f"/api/imaging/studies/{study_id}/findings"),
        ("get", f"/api/imaging/studies/{study_id}/report/pages/1/preview"),
        ("delete", f"/api/imaging/studies/{study_id}"),
    ]:
        response = getattr(api_client, method)(path, headers=other)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"

    upload = api_client.post(
        f"/api/imaging/studies/{study_id}/report",
        files={"file": ("x.pdf", _pdf(IMAGING_TEXT), "application/pdf")},
        headers=other,
    )
    assert upload.status_code == 404

    finding_id = api_client.get(f"/api/imaging/studies/{study_id}/findings").json()["findings"][0]["finding_id"]
    explain = api_client.post("/api/imaging/findings/explain", json={"finding_id": finding_id}, headers=other)
    assert explain.status_code == 404

    compare = api_client.post(
        "/api/imaging/compare",
        json={"document_id_a": owned["document_id"], "document_id_b": owned["document_id"]},
        headers=other,
    )
    assert compare.status_code == 404

    assert api_client.get("/api/imaging/studies", headers=other).json()["studies"] == []
    modalities = api_client.get("/api/imaging/modalities", headers=other).json()["modalities"]
    assert all(row["study_count"] == 0 for row in modalities)


def test_timeline_and_search_are_isolated(api_client, other_user_headers):
    _confirmed_lab_document(api_client)
    _verified_study(api_client)

    assert api_client.get("/api/timeline").json()["total_matched"] == 2
    assert api_client.get("/api/timeline", headers=other_user_headers).json()["total_matched"] == 0

    assert api_client.get("/api/search", params={"q": "a1c"}).json()["total"] >= 1
    assert api_client.get("/api/search", params={"q": "a1c"}, headers=other_user_headers).json()["total"] == 0
    assert api_client.get("/api/search", params={"q": "effusion"}, headers=other_user_headers).json()["total"] == 0


def test_medications_are_isolated(api_client, other_user_headers):
    import src.medication_workspace as medication_workspace_module

    fields = [{"key": "medication_name", "label": "Medication name", "value": "Amoxicillin", "confidence": "clearly_visible"}]
    state = medication_workspace_module.MedicationState(
        medication_id="med-owned",
        source="typed",
        status="review_required",
        fields=[medication_workspace_module.MedicationField(**f) for f in fields],
        confirmed=False,
    )
    save_owned_medication_session(api_client, state)
    other = other_user_headers

    assert api_client.get("/api/medications/v2/med-owned", headers=other).status_code == 404
    blocked = api_client.post(
        "/api/medications/v2/med-owned/confirm",
        json={"fields": fields, "reviewed_name_strength_instructions": True},
        headers=other,
    )
    assert blocked.status_code == 404

    confirmed = api_client.post(
        "/api/medications/v2/med-owned/confirm",
        json={"fields": fields, "reviewed_name_strength_instructions": True},
    )
    assert confirmed.status_code == 200
    assert api_client.get("/api/medications/v2/med-owned/record").status_code == 200
    assert api_client.get("/api/medications/v2/med-owned/record", headers=other).status_code == 404


@pytest.mark.parametrize("path", ["/api/timeline", "/api/imaging/studies", "/api/labs/summary"])
def test_unowned_legacy_rows_are_visible_to_nobody(api_client, path):
    from src.database.models import ImagingStudy
    from src.database.session import session_scope

    with session_scope() as session:
        session.add(ImagingStudy(modality="ct", verification_status="verified", owner_id=None))

    body = api_client.get(path).json()
    rows = body.get("entries", body.get("studies", body.get("points")))
    assert rows == []
