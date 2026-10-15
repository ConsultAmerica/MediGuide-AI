"""End-to-end extraction integrity on the synthetic three-visit lab report.

Upload -> process -> confirm through the real API, then check every
measurement's name, value, unit, reference range, collection date and
source page, so a parser or mapping regression can't reach the timeline.
"""

from __future__ import annotations

import pymupdf
import pytest

EXPECTED = {
    1: ("2026-01-15", {"Hemoglobin A1C": ("6.2", "%", "<5.7"), "Hemoglobin": ("13.1", "g/dL", "12.0-15.5"),
                       "Glucose": ("96", "mg/dL", "70-99"), "WBC": ("6.1", "10^3/uL", "4.0-11.0"),
                       "Platelets": ("238", "10^3/uL", "150-400")}),
    2: ("2026-04-12", {"Hemoglobin A1C": ("6.5", "%", "<5.7"), "Hemoglobin": ("13.0", "g/dL", "12.0-15.5"),
                       "Glucose": ("101", "mg/dL", "70-99"), "WBC": ("6.3", "10^3/uL", "4.0-11.0"),
                       "Platelets": ("241", "10^3/uL", "150-400")}),
    3: ("2026-08-12", {"Hemoglobin A1C": ("6.7", "%", "<5.7"), "Hemoglobin": ("12.9", "g/dL", "12.0-15.5"),
                       "Glucose": ("99", "mg/dL", "70-99"), "WBC": ("6.4", "10^3/uL", "4.0-11.0"),
                       "Platelets": ("242", "10^3/uL", "150-400")}),
}


def _upload_and_process(client, pdf_bytes: bytes, name: str = "labs.pdf") -> dict:
    uploaded = client.post("/api/documents/v2/upload", files={"file": (name, pdf_bytes, "application/pdf")}).json()
    state = client.post(f"/api/documents/v2/{uploaded['document_id']}/process").json()
    assert state["status"] == "review_required"
    return state


def _confirm(client, state: dict, fields: list[dict], **extra):
    return client.post(
        f"/api/documents/v2/{state['document_id']}/confirm",
        json={"fields": fields, "reviewed_names_values_units_dates": True, **extra},
    )


def _pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def sample_state(api_client):
    pdf = api_client.get("/api/documents/v2/sample/lab-report").content
    return _upload_and_process(api_client, pdf, "sample-lab-report.pdf")


def test_every_sample_measurement_is_extracted_exactly_with_its_source_page(sample_state):
    fields = sample_state["fields"]
    for page, (date, measurements) in EXPECTED.items():
        on_page = [f for f in fields if f["page_number"] == page]
        found = {f["label"]: (f["value"], f["unit"], f["reference_range"]) for f in on_page if f["status"] != "not_applicable"}
        assert found == measurements, f"page {page}"
        for field in on_page:
            if field["status"] != "not_applicable":
                assert field["label"] in field["source_text"]
                assert field["value"] in field["source_text"]
                assert field["confidence"] == "clearly_visible"
                assert field["extraction_method"] == "native_text"
        dates = [f for f in on_page if f["status"] == "not_applicable"]
        assert [(d["label"], d["value"]) for d in dates] == [("Collection date", date)]


def test_no_sample_field_carries_a_date_or_range_fragment_as_a_value_or_unit(sample_state):
    for field in sample_state["fields"]:
        if field["status"] == "not_applicable":
            continue
        assert not field["unit"].startswith(("-", "/"))
        assert "-" not in field["value"] and "/" not in field["value"]
        assert "date" not in field["label"].lower()
        assert "range" not in field["label"].lower()


def test_confirmed_sample_charts_each_value_on_its_own_collection_date_and_page(api_client, sample_state):
    assert _confirm(api_client, sample_state, sample_state["fields"]).status_code == 200
    points = api_client.get("/api/labs/timeline/hemoglobin_a1c").json()["points"]
    charted = sorted((p["collection_date"], p["value"], p["unit"], p["reference_range"], p.get("page_number")) for p in points)
    assert charted == [
        ("2026-01-15", 6.2, "%", "<5.7", 1),
        ("2026-04-12", 6.5, "%", "<5.7", 2),
        ("2026-08-12", 6.7, "%", "<5.7", 3),
    ]


def test_messy_report_metadata_never_becomes_a_measurement(api_client):
    text = (
        "Synthetic Lab Report - Page 1 of 1\n"
        "Specimen collected: 01/15/2026\n"
        "Phone: 555-0100\n"
        "Age: 45 yrs\n"
        "Glucose 101 H mg/dL Ref 70-99\n"
        "Reference range: 4.0-11.0\n"
    )
    fields = _upload_and_process(api_client, _pdf(text))["fields"]
    measurements = [f for f in fields if f["status"] != "not_applicable"]
    assert [(f["label"], f["value"], f["unit"], f["reference_range"]) for f in measurements] == [
        ("Glucose", "101", "mg/dL", "70-99"),
    ]
    assert measurements[0]["status"] == "flagged_high_on_report"
    dates = [f for f in fields if f["status"] == "not_applicable"]
    assert [(d["label"], d["value"]) for d in dates] == [("Collection date", "01/15/2026")]


def test_an_unreadable_result_row_is_flagged_for_review_and_never_charted(api_client):
    text = "Collection date: 2026-02-01\nHemoglobin A1C 6.1 % Ref <5.7\nGlucose 96 mg/dL 70-99 12\n"
    state = _upload_and_process(api_client, _pdf(text))
    unread = [f for f in state["fields"] if f["confidence"] == "could_not_read"]
    assert len(unread) == 1
    assert unread[0]["label"] == "Unread line"
    assert unread[0]["value"] == ""
    assert unread[0]["source_text"] == "Glucose 96 mg/dL 70-99 12"

    assert _confirm(api_client, state, state["fields"]).status_code == 200
    assert api_client.get("/api/labs/timeline/glucose").json()["count"] == 0
    assert api_client.get("/api/labs/timeline/hemoglobin_a1c").json()["count"] == 1


def test_a_tracked_test_confirmed_without_a_value_is_not_charted(api_client):
    state = _upload_and_process(api_client, _pdf("Collection date: 2026-03-01\nGlucose 96 mg/dL Ref 70-99\n"))
    emptied = [{**f, "value": ""} if f["label"] == "Glucose" else f for f in state["fields"]]
    assert _confirm(api_client, state, emptied).status_code == 200
    assert api_client.get("/api/labs/timeline/glucose").json()["count"] == 0
