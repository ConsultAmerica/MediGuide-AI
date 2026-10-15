from __future__ import annotations

import pymupdf


def _make_report_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


def _create_study(client):
    response = client.post(
        "/api/imaging/studies",
        json={"modality": "mri", "body_region": "Right knee", "study_date": "2026-09-02"},
    )
    assert response.status_code == 200
    return response.json()["study_id"]


REPORT_TEXT = "EXAM: MRI Right Knee\nFINDINGS: Small joint effusion.\nIMPRESSION: Small joint effusion.\n"


def test_status_is_idle_before_any_report_upload(api_client):
    study_id = _create_study(api_client)
    response = api_client.get(f"/api/imaging/studies/{study_id}/report/status")
    assert response.status_code == 200
    assert response.json()["status"] == "idle"


def test_status_goes_idle_again_once_an_upload_succeeds(api_client):
    """pending_report_document_id only tracks an in-flight or just-failed
    attempt (see its model docstring) — once an attempt succeeds, the
    report itself is already visible via the study's report_document_id/
    sections, so the pending pointer clears rather than lingering on
    "completed" forever."""
    study_id = _create_study(api_client)
    upload = api_client.post(
        f"/api/imaging/studies/{study_id}/report",
        files={"file": ("report.pdf", _make_report_pdf(REPORT_TEXT), "application/pdf")},
    )
    assert upload.status_code == 200

    response = api_client.get(f"/api/imaging/studies/{study_id}/report/status")
    assert response.status_code == 200
    assert response.json()["status"] == "idle"


def test_status_reflects_a_failed_attempt_for_retry_processing(api_client, monkeypatch):
    """A failed attempt must stay visible via the status route — this is
    what a "Retry processing" screen polls before the user clicks retry."""
    import src.imaging as imaging_module

    def _broken(*args, **kwargs):
        raise RuntimeError("simulated extraction failure")

    monkeypatch.setattr(imaging_module, "_read_report", _broken)

    study_id = _create_study(api_client)
    upload = api_client.post(
        f"/api/imaging/studies/{study_id}/report",
        files={"file": ("report.pdf", _make_report_pdf(REPORT_TEXT), "application/pdf")},
    )
    assert upload.status_code == 422

    response = api_client.get(f"/api/imaging/studies/{study_id}/report/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["safe_error_message"]


def test_status_returns_404_for_an_unknown_study(api_client):
    response = api_client.get("/api/imaging/studies/does-not-exist/report/status")
    assert response.status_code == 404
