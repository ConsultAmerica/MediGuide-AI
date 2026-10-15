"""Stage F3.4: lab normalization, verified trends, duplicates and source references.

Covers the reviewed alias list (clinically different tests stay apart),
values that must never be plotted as plain numbers, units that are never
silently mixed, collection vs report dates, repeated results across reports
and the provenance each result carries back to its source page.
"""

from __future__ import annotations

import uuid

import pytest

from src.labs.normalization import (
    normalize_test_name,
    normalize_unit,
    parse_reference_range,
    parse_value,
    unit_key,
)


# ------------------------------------------------------------ normalization

@pytest.mark.parametrize("printed", ["HbA1c", "Hemoglobin A1c", "HEMOGLOBIN A1C", "Glycated hemoglobin", "Hemoglobin A1c (HbA1c)"])
def test_a1c_aliases_share_one_code(printed):
    assert normalize_test_name(printed) == "hemoglobin_a1c"


def test_fasting_glucose_is_not_merged_with_glucose():
    assert normalize_test_name("Fasting glucose") == "glucose_fasting"
    assert normalize_test_name("Glucose, Fasting") == "glucose_fasting"
    assert normalize_test_name("Glucose") == "glucose"


def test_clinically_different_tests_stay_apart():
    assert normalize_test_name("Hemoglobin") != normalize_test_name("Hemoglobin A1c")
    assert normalize_test_name("eGFR") != normalize_test_name("Creatinine")
    assert normalize_test_name("LDL") == normalize_test_name("LDL Cholesterol") == "ldl_cholesterol"
    assert normalize_test_name("Bilirubin, Direct") != normalize_test_name("Bilirubin, Total")


def test_unknown_test_keeps_its_own_identity():
    assert normalize_test_name("Vitamin B12") == "vitamin_b12"
    assert normalize_test_name("Lipoprotein (a)") == "lipoprotein_a"


@pytest.mark.parametrize("text,numeric,qualifier", [
    ("6.7", 6.7, ""),
    ("6.7%", 6.7, ""),
    ("1,200", 1200.0, ""),
    ("13.2 g/dL", 13.2, ""),
    ("<0.5", None, "<"),
    ("> 90", None, ">"),
    ("Positive", None, ""),
    ("1.0-2.0", None, ""),
    ("", None, ""),
])
def test_only_plain_numbers_are_plottable(text, numeric, qualifier):
    parsed = parse_value(text)
    assert parsed.numeric == numeric
    assert parsed.qualifier == qualifier


def test_unit_spellings_compare_equal_without_conversion():
    assert unit_key("K/uL") == unit_key("10^3/uL") == unit_key("x10E3/uL") == unit_key("10^9/L")
    assert unit_key("mg/dl") == unit_key("mg/dL")
    assert unit_key("IU/L") == unit_key("U/L")
    assert unit_key("mg/dL") != unit_key("mmol/L")
    # The stored unit keeps its printed notation; only casing is tidied.
    assert normalize_unit("K/uL") == "K/uL"
    assert normalize_unit("mg/dl") == "mg/dL"


@pytest.mark.parametrize("text,bounds", [
    ("70 - 99", (70.0, 99.0)),
    ("10 to 20", (10.0, 20.0)),
    ("(0.6-1.2)", (0.6, 1.2)),
    ("<200", (None, 200.0)),
    (">= 60", (60.0, None)),
    ("Negative", (None, None)),
    ("99 - 70", (None, None)),
    ("70-99 if fasting, <140 otherwise", (None, None)),
])
def test_reference_bounds_only_when_unambiguous(text, bounds):
    assert parse_reference_range(text) == bounds


# ------------------------------------------------- confirmed observations

def _field(label, value, unit="", reference_range="", page=1, **extra):
    return {
        "field_id": f"f-{uuid.uuid4().hex[:8]}", "label": label, "value": value, "unit": unit,
        "reference_range": reference_range, "status": extra.pop("status", "unknown"),
        "confidence": "clearly_visible", "page_number": page, "source_text": f"{label} {value} {unit}".strip(),
        "extraction_method": "native_text", **extra,
    }


def _date(label, value, page=1):
    return _field(label, value, status="not_applicable", page=page)


def _confirm(session, owner, fields, name="report.pdf"):
    from src.database.repository import upsert_confirmed_document

    document_id = uuid.uuid4().hex
    upsert_confirmed_document(
        session, document_id=document_id, filename=name, page_count=1,
        pages=[{"page_number": 1, "preview_url": ""}], fields=fields, owner_id=owner,
    )
    session.flush()
    return document_id


@pytest.fixture()
def owner(db_session):
    return f"owner-{uuid.uuid4().hex[:8]}"


def _timeline(code, owner):
    from src.database.repository import get_timeline
    from src.database.session import session_scope

    with session_scope() as session:
        return get_timeline(session, code, owner)


def test_every_confirmed_result_reaches_labs_not_only_a_fixed_list(db_session, owner):
    from src.database.repository import list_tracked_tests
    from src.database.session import session_scope

    with session_scope() as session:
        _confirm(session, owner, [
            _date("Collection date", "03/15/2026"),
            _field("Sodium", "139", "mmol/L", "136 - 145"),
            _field("Vitamin B12", "450", "pg/mL", "200 - 900"),
            _field("Specimen", "Serum"),          # free text: not a result
            _field("Unread line", ""),            # nothing was read
        ])
    with session_scope() as session:
        tests = {t["test_code"]: t for t in list_tracked_tests(session, owner)}
    assert tests["sodium"]["has_data"] and tests["sodium"]["display_name"] == "Sodium"
    assert tests["vitamin_b12"]["has_data"] and tests["vitamin_b12"]["display_name"] == "Vitamin B12"
    assert "specimen" not in tests and "unread_line" not in tests
    assert not tests["hemoglobin_a1c"]["has_data"]   # core tests still offered


def test_dates_are_labelled_by_source_and_never_taken_from_a_birth_date(db_session, owner):
    from src.database.session import session_scope

    with session_scope() as session:
        _confirm(session, owner, [_date("Date of birth", "01/02/1960"), _date("Collection date", "03/15/2026"),
                                  _field("Glucose", "101", "mg/dL")])
        _confirm(session, owner, [_date("Report date", "04/20/2026"), _field("Glucose", "99", "mg/dL")])
        _confirm(session, owner, [_date("Date of birth", "01/02/1960"), _field("Glucose", "97", "mg/dL")])

    points = _timeline("glucose", owner)
    by_value = {p["value_text"]: p for p in points}
    assert by_value["101"]["date"] == "2026-03-15" and by_value["101"]["date_source"] == "collection"
    assert by_value["101"]["collection_date"] == "2026-03-15"
    assert by_value["99"]["date_source"] == "report" and by_value["99"]["collection_date"] is None
    # No confirmed result date: undated, listed last, not plotted, nothing invented.
    assert by_value["97"]["date"] is None and by_value["97"]["not_plotted_reason"] == "no_date"
    assert points[-1]["value_text"] == "97"


def test_the_same_result_in_two_reports_is_marked_as_a_duplicate(db_session, owner):
    from src.database.session import session_scope

    fields = lambda: [_date("Collection date", "03/15/2026"), _field("HbA1c", "6.7", "%", "4.0 - 5.6")]  # noqa: E731
    with session_scope() as session:
        _confirm(session, owner, fields(), name="lab-march.pdf")
        _confirm(session, owner, fields(), name="lab-march-copy.pdf")

    first, second = _timeline("hemoglobin_a1c", owner)
    assert first["plotted"] and first["duplicate_of"] is None
    assert second["duplicate_of"] == first["observation_id"]
    assert second["duplicate_document_name"] == "lab-march.pdf"
    assert not second["plotted"] and second["not_plotted_reason"] == "duplicate"


def test_different_values_on_the_same_date_are_called_out_not_merged(db_session, owner):
    from src.database.session import session_scope

    with session_scope() as session:
        _confirm(session, owner, [_date("Collection date", "03/15/2026"), _field("Glucose", "101", "mg/dL"),
                                  _field("Glucose", "140", "mg/dL")])
    points = _timeline("glucose", owner)
    assert {p["value_text"] for p in points} == {"101", "140"}
    assert all(p["plotted"] for p in points)
    assert {tuple(p["conflicting_values"]) for p in points} == {("140",), ("101",)}


def test_units_are_never_mixed_in_a_trend(db_session, owner):
    from src.database.session import session_scope

    with session_scope() as session:
        _confirm(session, owner, [_date("Collection date", "01/10/2026"), _field("Glucose", "101", "mg/dL")])
        _confirm(session, owner, [_date("Collection date", "02/10/2026"), _field("Glucose", "105", "mg/dl")])
        _confirm(session, owner, [_date("Collection date", "03/10/2026"), _field("Glucose", "5.4", "mmol/L")])
        _confirm(session, owner, [_date("Collection date", "04/10/2026"), _field("Glucose", "110", "mg/dL")])

    points = _timeline("glucose", owner)
    assert [p["value_text"] for p in points] == ["101", "105", "5.4", "110"]
    assert [p["plotted"] for p in points] == [True, True, False, True]
    assert points[2]["not_plotted_reason"] == "different_unit"
    assert points[2]["unit"] == "mmol/L"                     # original unit kept
    # Change is only ever computed between comparable plotted results.
    assert points[1]["change_from_previous"] == 4.0
    assert points[2]["change_from_previous"] is None
    assert points[3]["change_from_previous"] == 5.0


def test_printed_bounds_and_text_results_are_listed_but_not_plotted(db_session, owner):
    from src.database.session import session_scope

    with session_scope() as session:
        _confirm(session, owner, [_date("Collection date", "03/15/2026"), _field("Creatinine", "<0.5", "mg/dL")])
        _confirm(session, owner, [_date("Collection date", "04/15/2026"), _field("Creatinine", "0.9", "mg/dL")])
    low, normal = _timeline("creatinine", owner)
    assert low["value"] is None and low["value_qualifier"] == "<"
    assert low["not_plotted_reason"] == "qualified_value"
    assert normal["plotted"] and normal["change_from_previous"] is None


def test_single_result_has_no_trend(db_session, owner):
    from src.database.session import session_scope

    with session_scope() as session:
        _confirm(session, owner, [_date("Collection date", "03/15/2026"), _field("TSH", "2.1", "mIU/L")])
    (only,) = _timeline("tsh", owner)
    assert only["plotted"] and only["change_from_previous"] is None and only["change_direction"] is None


# ---------------------------------------------------- through the real API

def test_api_result_carries_its_source_and_review_history(api_client):
    from tests.test_review_workflow import _lab_pdf

    uploaded = api_client.post("/api/documents/v2/upload", files={"file": ("labs.pdf", _lab_pdf(), "application/pdf")}).json()
    state = api_client.post(f"/api/documents/v2/{uploaded['document_id']}/process").json()
    edited = [{**f, "value": "113"} if f["label"] == "Glucose" else f for f in state["fields"]]
    confirmed = api_client.post(f"/api/documents/v2/{state['document_id']}/confirm",
                                json={"fields": edited, "reviewed_names_values_units_dates": True})
    assert confirmed.status_code == 200

    tests = {t["test_code"]: t for t in api_client.get("/api/labs/tests").json()["tests"]}
    assert tests["sodium"]["has_data"]          # not on the old fixed list

    timeline = api_client.get("/api/labs/timeline/glucose").json()
    assert timeline["series_unit"] == "mg/dL" and timeline["plotted_count"] == 1
    (point,) = timeline["points"]
    assert point["original_name"] == "Glucose"
    assert point["confirmed_value"] == "113" and point["extracted_value"] == "112"
    assert point["review_status"] == "corrected" and point["reviewed_at"]
    assert point["source_flag"] == "H"
    assert point["date"] == "2026-03-15" and point["date_source"] == "collection"
    assert point["source_page"] == 1 and point["source_text"]
    assert point["source_bbox"] and len(point["source_bbox"]) == 4

    detail = api_client.get(f"/api/labs/observations/{point['observation_id']}").json()
    assert detail["extracted_value"] == "112" and detail["source_bbox"] == point["source_bbox"]


def test_another_account_sees_none_of_these_results(api_client, other_user_headers):
    from tests.test_review_workflow import _lab_pdf

    uploaded = api_client.post("/api/documents/v2/upload", files={"file": ("labs.pdf", _lab_pdf(), "application/pdf")}).json()
    state = api_client.post(f"/api/documents/v2/{uploaded['document_id']}/process").json()
    api_client.post(f"/api/documents/v2/{state['document_id']}/confirm",
                    json={"fields": state["fields"], "reviewed_names_values_units_dates": True})

    other = api_client.get("/api/labs/tests", headers=other_user_headers).json()["tests"]
    assert not any(t["has_data"] for t in other)
    assert api_client.get("/api/labs/timeline/sodium", headers=other_user_headers).json()["points"] == []
    assert api_client.get("/api/labs/summary", headers=other_user_headers).json()["points"] == []
