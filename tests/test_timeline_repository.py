from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from src.database.models import (
    Document,
    ImagingStudy,
    LabObservation,
    MedicationRecord,
)
from src.database.timeline_repository import get_timeline_entries, list_timeline_entries


def test_empty_database_returns_no_entries(db_session):
    with db_session.session_scope() as session:
        assert get_timeline_entries(session, owner_id=None) == []


def test_unconfirmed_document_never_appears(db_session):
    with db_session.session_scope() as session:
        session.add(Document(id="doc-1", filename="draft.pdf", confirmed=False))
    with db_session.session_scope() as session:
        assert get_timeline_entries(session, owner_id=None) == []


def test_unverified_imaging_study_never_appears(db_session):
    with db_session.session_scope() as session:
        session.add(Document(id="doc-1", filename="report.pdf", confirmed=True))
        session.add(
            ImagingStudy(
                id="study-1",
                modality="mri",
                report_document_id="doc-1",
                verification_status="unverified",
            )
        )
    with db_session.session_scope() as session:
        entries = get_timeline_entries(session, owner_id=None)
    # The document itself is confirmed and has no lab observations, so it
    # still surfaces as a generic Document entry — it just must not also
    # (or instead) appear as an Imaging entry while unverified.
    assert all(entry["category"] != "imaging" for entry in entries)


def test_imaging_report_document_is_not_double_counted(db_session):
    with db_session.session_scope() as session:
        session.add(Document(id="doc-1", filename="mri_report.pdf", confirmed=True))
        session.add(
            ImagingStudy(
                id="study-1",
                modality="mri",
                body_region="Right knee",
                study_date=date(2026, 9, 2),
                report_document_id="doc-1",
                verification_status="verified",
            )
        )
    with db_session.session_scope() as session:
        entries = get_timeline_entries(session, owner_id=None)

    assert len(entries) == 1
    assert entries[0]["category"] == "imaging"
    assert entries[0]["title"] == "MRI — Right knee"
    assert entries[0]["link"] == {"type": "imaging_study", "id": "study-1"}
    assert entries[0]["verified"] is True


def test_document_with_lab_observations_becomes_laboratory_entry(db_session):
    with db_session.session_scope() as session:
        session.add(
            Document(
                id="doc-1",
                filename="labs.pdf",
                confirmed=True,
                report_date=date(2026, 8, 12),
            )
        )
        session.add(
            LabObservation(
                document_id="doc-1",
                field_id="00000000-0000-0000-0000-000000000001",
                page_number=1,
                test_code="hemoglobin_a1c",
                test_name="Hemoglobin A1C",
                value_numeric=6.7,
                value_text="6.7",
                unit="%",
                report_date=date(2026, 8, 12),
            )
        )
        session.add(
            LabObservation(
                document_id="doc-1",
                field_id="00000000-0000-0000-0000-000000000002",
                page_number=1,
                test_code="glucose",
                test_name="Glucose",
                value_numeric=108,
                value_text="108",
                unit="mg/dL",
                report_date=date(2026, 8, 12),
            )
        )
    with db_session.session_scope() as session:
        entries = get_timeline_entries(session, owner_id=None)

    assert len(entries) == 1
    entry = entries[0]
    assert entry["category"] == "laboratory"
    assert entry["date"] == "2026-08-12"
    assert entry["verification_label"] == "2 verified measurements"
    assert "Hemoglobin A1C" in entry["subtitle"]
    assert "6.7" in entry["subtitle"]
    assert "Glucose" in entry["subtitle"]
    assert entry["link"] == {"type": "document", "id": "doc-1"}


def test_document_without_lab_observations_becomes_generic_document_entry(db_session):
    with db_session.session_scope() as session:
        session.add(
            Document(
                id="doc-1",
                filename="referral.pdf",
                confirmed=True,
                report_date=date(2026, 7, 1),
            )
        )
    with db_session.session_scope() as session:
        entries = get_timeline_entries(session, owner_id=None)

    assert len(entries) == 1
    assert entries[0]["category"] == "document"
    assert entries[0]["title"] == "referral.pdf"
    assert entries[0]["verification_label"] == "Confirmed"


def test_medication_record_becomes_medication_entry(db_session):
    with db_session.session_scope() as session:
        session.add(
            MedicationRecord(
                id="med-1",
                medication_name="Amoxicillin",
                strength="500mg",
                source="typed",
            )
        )
    with db_session.session_scope() as session:
        entries = get_timeline_entries(session, owner_id=None)

    assert len(entries) == 1
    entry = entries[0]
    assert entry["category"] == "medication"
    assert entry["subtitle"] == "Amoxicillin"
    assert entry["verification_label"] == "User verified"
    assert entry["link"] == {"type": "medication", "id": "med-1"}


def test_entries_sorted_descending_with_undated_last(db_session):
    with db_session.session_scope() as session:
        session.add(Document(id="doc-old", filename="a.pdf", confirmed=True, report_date=date(2025, 1, 1)))
        session.add(Document(id="doc-new", filename="b.pdf", confirmed=True, report_date=date(2026, 9, 1)))
        session.add(Document(id="doc-undated", filename="c.pdf", confirmed=True, report_date=None))
    with db_session.session_scope() as session:
        entries = get_timeline_entries(session, owner_id=None)

    assert [e["link"]["id"] for e in entries] == ["doc-new", "doc-old", "doc-undated"]


def test_lab_subtitle_prefers_headline_tests_when_present(db_session):
    with db_session.session_scope() as session:
        session.add(Document(id="doc-1", filename="labs.pdf", confirmed=True, report_date=date(2026, 8, 12)))
        for code, name, value in [
            ("creatinine", "Creatinine", "0.9"),
            ("wbc", "WBC", "6.4"),
            ("hemoglobin_a1c", "Hemoglobin A1C", "6.7"),
            ("glucose", "Glucose", "108"),
        ]:
            session.add(
                LabObservation(
                    document_id="doc-1",
                    field_id=f"field-{code}",
                    page_number=1,
                    test_code=code,
                    test_name=name,
                    value_text=value,
                    report_date=date(2026, 8, 12),
                )
            )
    with db_session.session_scope() as session:
        entries = get_timeline_entries(session, owner_id=None)

    subtitle = entries[0]["subtitle"]
    assert "Hemoglobin A1C" in subtitle
    assert "Glucose" in subtitle
    assert "Creatinine" not in subtitle
    assert "WBC" not in subtitle


# --------------------------------------------------------------------------
# Phase 2: additive TimelineEvent fields
# --------------------------------------------------------------------------


def test_event_type_and_source_fields_mirror_category_and_link(db_session):
    with db_session.session_scope() as session:
        session.add(Document(id="doc-1", filename="referral.pdf", confirmed=True))
    with db_session.session_scope() as session:
        entries = get_timeline_entries(session, owner_id=None)

    entry = entries[0]
    assert entry["event_type"] == entry["category"]
    assert entry["source_type"] == entry["link"]["type"]
    assert entry["source_id"] == entry["link"]["id"]


def test_document_id_and_page_number_per_category(db_session):
    with db_session.session_scope() as session:
        # Imaging.
        session.add(Document(id="img-doc", filename="mri_report.pdf", confirmed=True))
        session.add(
            ImagingStudy(
                id="study-1",
                modality="mri",
                report_document_id="img-doc",
                verification_status="verified",
            )
        )
        # Laboratory, single shared page.
        session.add(Document(id="lab-doc", filename="labs.pdf", confirmed=True, report_date=date(2026, 8, 12)))
        session.add(
            LabObservation(
                document_id="lab-doc", field_id="field-a1c", page_number=2,
                test_code="hemoglobin_a1c", test_name="Hemoglobin A1C", value_text="6.7",
                report_date=date(2026, 8, 12),
            )
        )
        session.add(
            LabObservation(
                document_id="lab-doc", field_id="field-glucose", page_number=2,
                test_code="glucose", test_name="Glucose", value_text="108",
                report_date=date(2026, 8, 12),
            )
        )
        # Laboratory, observations span two pages -> page_number must be None.
        session.add(Document(id="multi-page-doc", filename="panel.pdf", confirmed=True, report_date=date(2026, 7, 1)))
        session.add(
            LabObservation(
                document_id="multi-page-doc", field_id="field-wbc", page_number=1,
                test_code="wbc", test_name="WBC", value_text="6.4",
                report_date=date(2026, 7, 1),
            )
        )
        session.add(
            LabObservation(
                document_id="multi-page-doc", field_id="field-plt", page_number=2,
                test_code="platelets", test_name="Platelets", value_text="250",
                report_date=date(2026, 7, 1),
            )
        )
        # Generic document.
        session.add(Document(id="generic-doc", filename="notes.pdf", confirmed=True, report_date=date(2026, 6, 1)))
        # Medication.
        session.add(MedicationRecord(id="med-1", medication_name="Amoxicillin", source="typed"))
    with db_session.session_scope() as session:
        entries = get_timeline_entries(session, owner_id=None)

    by_id = {entry["entry_id"]: entry for entry in entries}

    imaging = by_id["imaging:study-1"]
    assert imaging["document_id"] == "img-doc"
    assert imaging["page_number"] is None
    assert imaging["route"] == "/workspace/imaging/study-1"

    lab = by_id["lab:lab-doc"]
    assert lab["document_id"] == "lab-doc"
    assert lab["page_number"] == 2
    assert lab["route"] == "/workspace/documents/lab-doc?page=2"

    multi_page_lab = by_id["lab:multi-page-doc"]
    assert multi_page_lab["page_number"] is None
    assert multi_page_lab["route"] == "/workspace/documents/multi-page-doc"

    generic = by_id["document:generic-doc"]
    assert generic["document_id"] == "generic-doc"
    assert generic["page_number"] == 1
    assert generic["route"] == "/workspace/documents/generic-doc"

    medication = by_id["medication:med-1"]
    assert medication["document_id"] is None
    assert medication["page_number"] is None
    assert medication["route"] == "/workspace/timeline"


def test_measurements_embedded_on_lab_entries_only(db_session):
    with db_session.session_scope() as session:
        session.add(Document(id="doc-1", filename="labs.pdf", confirmed=True, report_date=date(2026, 8, 12)))
        session.add(
            LabObservation(
                document_id="doc-1", field_id="field-a1c", page_number=1,
                test_code="hemoglobin_a1c", test_name="Hemoglobin A1C", value_text="6.7",
                unit="%", report_date=date(2026, 8, 12),
            )
        )
        session.add(Document(id="doc-2", filename="referral.pdf", confirmed=True))
        session.add(MedicationRecord(id="med-1", medication_name="Amoxicillin", source="typed"))
    with db_session.session_scope() as session:
        entries = get_timeline_entries(session, owner_id=None)

    by_id = {entry["entry_id"]: entry for entry in entries}
    measurements = by_id["lab:doc-1"]["measurements"]
    assert measurements == [
        {
            "test_code": "hemoglobin_a1c",
            "test_name": "Hemoglobin A1C",
            "value_text": "6.7",
            "value_numeric": None,
            "unit": "%",
            "range_status": "unknown",
            "page_number": 1,
            "field_id": "field-a1c",
        }
    ]
    assert by_id["document:doc-2"]["measurements"] is None
    assert by_id["medication:med-1"]["measurements"] is None


def test_sort_tiebreak_by_entry_id_when_dates_equal(db_session):
    with db_session.session_scope() as session:
        session.add(Document(id="doc-b", filename="b.pdf", confirmed=True, report_date=date(2026, 8, 12)))
        session.add(Document(id="doc-a", filename="a.pdf", confirmed=True, report_date=date(2026, 8, 12)))
    with db_session.session_scope() as session:
        entries = get_timeline_entries(session, owner_id=None)

    same_date_ids = [e["entry_id"] for e in entries if e["date"] == "2026-08-12"]
    # entry_id is "document:<id>" for both — reverse=True on the tuple means
    # the lexicographically larger entry_id (doc-b) sorts first.
    assert same_date_ids == ["document:doc-b", "document:doc-a"]


def test_document_with_both_imaging_link_and_lab_observations_appears_once_as_imaging(db_session):
    """A document that is simultaneously an imaging report's source AND
    (hypothetically) carries LabObservation rows must still appear exactly
    once, as imaging — never twice, never as laboratory instead."""
    with db_session.session_scope() as session:
        session.add(Document(id="doc-1", filename="mixed.pdf", confirmed=True, report_date=date(2026, 9, 2)))
        session.add(
            ImagingStudy(
                id="study-1",
                modality="mri",
                report_document_id="doc-1",
                verification_status="verified",
            )
        )
        session.add(
            LabObservation(
                document_id="doc-1", field_id="field-a1c", page_number=1,
                test_code="hemoglobin_a1c", test_name="Hemoglobin A1C", value_text="6.7",
                report_date=date(2026, 9, 2),
            )
        )
    with db_session.session_scope() as session:
        entries = get_timeline_entries(session, owner_id=None)

    doc_1_entries = [e for e in entries if e.get("document_id") == "doc-1"]
    assert len(doc_1_entries) == 1
    assert doc_1_entries[0]["category"] == "imaging"


# --------------------------------------------------------------------------
# Phase 2: list_timeline_entries() — filters and pagination
# --------------------------------------------------------------------------


def _seed_mixed_entries(db_session):
    with db_session.session_scope() as session:
        session.add(Document(id="lab-doc", filename="labs.pdf", confirmed=True, report_date=date(2026, 8, 12)))
        session.add(
            LabObservation(
                document_id="lab-doc", field_id="field-a1c", page_number=1,
                test_code="hemoglobin_a1c", test_name="Hemoglobin A1C", value_text="6.7",
                report_date=date(2026, 8, 12),
            )
        )
        session.add(Document(id="img-doc", filename="mri_report.pdf", confirmed=True))
        session.add(
            ImagingStudy(
                id="study-1", modality="mri", body_region="Right knee",
                study_date=date(2026, 9, 2),
                report_document_id="img-doc", verification_status="verified",
            )
        )
        # Explicit confirmed_at (rather than relying on the column's
        # server_default=now()) so date-range filter tests are deterministic
        # regardless of what day the suite actually runs.
        session.add(
            MedicationRecord(
                id="med-1", medication_name="Amoxicillin", source="typed",
                confirmed_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
            )
        )


def test_list_timeline_entries_filters_by_event_type(db_session):
    _seed_mixed_entries(db_session)
    with db_session.session_scope() as session:
        result = list_timeline_entries(session, owner_id=None, event_type="imaging")

    assert [e["category"] for e in result["entries"]] == ["imaging"]
    assert result["total_matched"] == 1


def test_list_timeline_entries_filters_by_date_range(db_session):
    _seed_mixed_entries(db_session)
    with db_session.session_scope() as session:
        result = list_timeline_entries(session, owner_id=None, date_from="2026-09-01", date_to="2026-09-30")

    # Only the imaging entry (Sep 2) falls in range; the Jul 28 medication
    # and the Aug 12 lab entry are both excluded.
    assert [e["category"] for e in result["entries"]] == ["imaging"]


def test_list_timeline_entries_filters_by_search(db_session):
    _seed_mixed_entries(db_session)
    with db_session.session_scope() as session:
        result = list_timeline_entries(session, owner_id=None, search="amoxicillin")

    assert [e["category"] for e in result["entries"]] == ["medication"]


def test_list_timeline_entries_pagination_cursor_is_stable_across_pages(db_session):
    _seed_mixed_entries(db_session)
    with db_session.session_scope() as session:
        page_one = list_timeline_entries(session, owner_id=None, limit=1)
    assert len(page_one["entries"]) == 1
    assert page_one["next_cursor"] is not None
    assert page_one["total_matched"] == 3

    with db_session.session_scope() as session:
        page_two = list_timeline_entries(session, owner_id=None, limit=1, cursor=page_one["next_cursor"])
    assert len(page_two["entries"]) == 1
    assert page_two["entries"][0]["entry_id"] != page_one["entries"][0]["entry_id"]

    with db_session.session_scope() as session:
        page_three = list_timeline_entries(session, owner_id=None, limit=1, cursor=page_two["next_cursor"])
    assert len(page_three["entries"]) == 1
    assert page_three["next_cursor"] is None

    seen_ids = {page_one["entries"][0]["entry_id"], page_two["entries"][0]["entry_id"], page_three["entries"][0]["entry_id"]}
    assert len(seen_ids) == 3  # no duplicates, no gaps across all 3 pages


def test_list_timeline_entries_invalid_cursor_raises(db_session):
    _seed_mixed_entries(db_session)
    with db_session.session_scope() as session:
        with pytest.raises(HTTPException):
            list_timeline_entries(session, owner_id=None, cursor="not-a-valid-cursor")
