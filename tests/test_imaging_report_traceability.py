"""Stage F3.5: imaging report classification, sections and traceable review.

Synthetic, de-identified report text only. Covers multi-page reports,
missing sections (never invented), mis-detected headings, the report's own
details, per-section review that can be resumed, correcting section
boundaries without adding words, and scanned reports read by local OCR.
"""

from __future__ import annotations


import pymupdf
import pytest

from src.imaging_sections import (
    ReportLine,
    classify_report,
    extract_report_details,
    find_sections,
    lines_from_text,
    split_report_sections,
)

# ----------------------------------------------------------------- splitter


def test_prose_that_starts_like_a_heading_is_not_a_new_section():
    text = (
        "FINDINGS:\n"
        "History of prior arthroscopy is noted.\n"
        "Examined structures show no acute fracture.\n"
        "Impression of the tendon on the bone is unchanged.\n"
        "IMPRESSION:\n"
        "No acute fracture.\n"
    )
    sections = split_report_sections(text)
    assert set(sections) == {"findings", "impression"}
    assert sections["findings"].splitlines() == [
        "History of prior arthroscopy is noted.",
        "Examined structures show no acute fracture.",
        "Impression of the tendon on the bone is unchanged.",
    ]


def test_signature_block_is_not_part_of_the_last_section():
    text = "IMPRESSION:\nNo acute disease.\nElectronically signed by: Dr. Example Reader\n03/02/2026 10:15"
    assert split_report_sections(text)["impression"] == "No acute disease."


def test_a_section_continues_across_pages_and_page_furniture_is_skipped():
    lines = [
        ReportLine(1, "FINDINGS:"),
        ReportLine(1, "The liver is normal in size."),
        ReportLine(1, "Page 1 of 2"),
        ReportLine(2, "The spleen is normal in size."),
        ReportLine(2, "IMPRESSION:"),
        ReportLine(2, "Normal abdominal ultrasound."),
    ]
    findings, impression = find_sections(lines)
    assert findings.text == "The liver is normal in size.\nThe spleen is normal in size."
    assert (findings.page_start, findings.page_end) == (1, 2)
    assert (impression.page_start, impression.page_end) == (2, 2)


def test_sample_disclaimer_footer_is_not_report_wording():
    lines = [
        ReportLine(1, "IMPRESSION:"),
        ReportLine(1, "No acute disease."),
        ReportLine(1, "Educational sample only — synthetic demo, not a real patient report."),
    ]
    (impression,) = find_sections(lines)
    assert impression.text == "No acute disease."


def test_missing_comparison_section_is_not_invented():
    sections = split_report_sections("EXAM: CT chest\nFINDINGS: Clear lungs.\nIMPRESSION: Normal.")
    assert "comparison" not in sections


# ----------------------------------------------------- classification/details


@pytest.mark.parametrize("exam,expected", [
    ("CT chest with contrast", "ct"),
    ("MRI of the right knee", "mri"),
    ("Ultrasound of the abdomen", "ultrasound"),
    ("Chest radiograph, PA and lateral views", "xray"),
    ("Bilateral screening mammogram with tomosynthesis", "mammography"),
])
def test_modality_is_read_from_the_exam_line(exam, expected):
    report = f"EXAM: {exam}\nFINDINGS: See text. Comparison with prior MRI.\nIMPRESSION: Normal."
    result = classify_report(report)
    assert result["modality"] == expected
    assert result["category"] == "radiology_report"


def test_a_lab_report_is_not_classified_as_radiology():
    lab = "Glucose 101 mg/dL 70-99\nSodium 139 mmol/L 136-145\nHemoglobin 13.2 g/dL 12-16\nALT 31 U/L 7-56\n"
    assert classify_report(lab)["category"] == "not_radiology_report"


def test_prose_without_headings_is_uncertain_not_forced():
    result = classify_report("Patient presented for evaluation. Everything looked fine.")
    assert result["category"] == "uncertain" and result["modality"] is None


def test_details_come_only_from_labelled_lines():
    lines = lines_from_text(
        "Date of birth: 01/02/1960\n"
        "Exam date: 03/02/2026\n"
        "Ordering physician: Dr. Example Orderer\n"
        "Facility: Example Imaging Center\n"
        "EXAM: MRI of the left knee without contrast\n"
        "FINDINGS: Small effusion.\n"
    )
    details = extract_report_details(lines)
    assert details["exam_date"]["value"] == "2026-03-02"
    assert details["ordering_clinician"]["value"] == "Dr. Example Orderer"
    assert details["facility"]["value"] == "Example Imaging Center"
    assert details["body_region"]["value"] == "Left knee"
    assert details["study_description"]["value"] == "MRI of the left knee without contrast"


def test_no_labelled_date_means_no_exam_date():
    details = extract_report_details(lines_from_text("Date of birth: 01/02/1960\nEXAM: CT head\nFINDINGS: Normal."))
    assert "exam_date" not in details


# --------------------------------------------------------- through the API


PAGE_ONE = [
    "Exam date: 03/02/2026",
    "Ordering physician: Dr. Example Orderer",
    "EXAM: CT chest with contrast",
    "CLINICAL HISTORY: Cough.",
    "FINDINGS:",
    "Patchy right upper lobe opacity.",
    "No pleural effusion.",
    "Page 1 of 2",
]
PAGE_TWO = [
    "Small mediastinal lymph node, unchanged.",
    "IMPRESSION:",
    "Right upper lobe opacity, compatible with pneumonia.",
    "RECOMMENDATIONS:",
    "Follow-up chest CT after treatment.",
    "Electronically signed by: Dr. Example Reader",
]


def _pdf(pages: list[list[str]]) -> bytes:
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page()
        for index, line in enumerate(lines):
            page.insert_text((72, 72 + index * 16), line, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture(autouse=True)
def no_vision(monkeypatch):
    """These reports are readable as text or by local OCR; the AI fallback
    must not be reached (and never is in CI)."""
    import src.imaging as imaging_module

    def _fail(*args, **kwargs):
        raise AssertionError("vision fallback should not run for readable reports")

    monkeypatch.setattr(imaging_module, "_extract_sections_via_vision", _fail)


def _study(client, modality="mri"):
    response = client.post("/api/imaging/studies", json={"modality": modality, "body_region": "Chest"})
    assert response.status_code == 200
    return response.json()["study_id"]


def _upload(client, study_id, data, name="report.pdf", content_type="application/pdf"):
    response = client.post(f"/api/imaging/studies/{study_id}/report", files={"file": (name, data, content_type)})
    assert response.status_code == 200, response.text
    return {s["section_type"]: s for s in client.get(f"/api/imaging/studies/{study_id}/report/sections").json()["sections"]}


def test_multi_page_report_links_each_section_and_finding_to_its_pages(api_client):
    study_id = _study(api_client)
    sections = _upload(api_client, study_id, _pdf([PAGE_ONE, PAGE_TWO]))

    findings = sections["findings"]
    assert findings["page_number"] == 1 and findings["page_end"] == 2
    assert findings["original_text"].splitlines() == [
        "Patchy right upper lobe opacity.", "No pleural effusion.", "Small mediastinal lymph node, unchanged.",
    ]
    assert {region["page"] for region in findings["source_regions"]} == {1, 2}
    assert all(r["width"] > 0 and len(r["bbox"]) == 4 for r in findings["source_regions"])
    assert sections["impression"]["page_number"] == 2
    assert sections["recommendations"]["original_text"] == "Follow-up chest CT after treatment."
    assert "comparison" not in sections
    assert all(s["extraction_method"] == "native_text" for s in sections.values())


def test_report_type_and_details_are_kept_and_a_mismatch_is_visible(api_client):
    study_id = _study(api_client, modality="mri")
    _upload(api_client, study_id, _pdf([PAGE_ONE, PAGE_TWO]))
    study = api_client.get(f"/api/imaging/studies/{study_id}").json()
    assert study["report_page_count"] == 2
    classification = study["report_details"]["classification"]
    assert classification["category"] == "radiology_report"
    assert classification["modality"] == "ct" and study["modality"] == "mri"   # flagged, not changed
    details = study["report_details"]["details"]
    assert details["exam_date"]["value"] == "2026-03-02" and details["exam_date"]["page"] == 1

    applied = api_client.post(f"/api/imaging/studies/{study_id}/report/details/apply",
                              json={"fields": ["modality", "study_date"]}).json()
    assert applied["modality"] == "ct" and applied["study_date"] == "2026-03-02"
    audit = applied["report_details"]["applied"]
    assert audit["modality"]["previous"] == "mri" and audit["modality"]["value"] == "ct"
    assert applied["report_details"]["classification"]["modality"] == "ct"   # original reading kept


def test_section_review_confirm_correct_reject_undo_and_resume(api_client):
    study_id = _study(api_client)
    _upload(api_client, study_id, _pdf([PAGE_ONE, PAGE_TWO]))
    url = f"/api/imaging/studies/{study_id}/report/sections"

    corrected = api_client.post(f"{url}/impression/decision", json={"decision": "confirmed", "text": "RUL opacity, likely pneumonia."}).json()
    impression = next(s for s in corrected["sections"] if s["section_type"] == "impression")
    assert impression["section_text"] == "RUL opacity, likely pneumonia."
    assert impression["original_text"] == "Right upper lobe opacity, compatible with pneumonia."
    assert impression["reviewed_at"] and corrected["verification_status"] == "partially_verified"

    api_client.post(f"{url}/recommendations/decision", json={"decision": "rejected"})
    # Leave and come back: decisions were saved as they were made.
    resumed = {s["section_type"]: s for s in api_client.get(url).json()["sections"]}
    assert resumed["impression"]["verification_status"] == "confirmed"
    assert resumed["recommendations"]["verification_status"] == "rejected"
    assert resumed["findings"]["verification_status"] == "unverified"

    for section_type in ("exam", "clinical_history", "findings"):
        result = api_client.post(f"{url}/{section_type}/decision", json={"decision": "confirmed"}).json()
    assert result["verification_status"] == "verified"            # rejected sections don't block

    undone = api_client.post(f"{url}/impression/decision", json={"decision": "unverified"}).json()
    impression = next(s for s in undone["sections"] if s["section_type"] == "impression")
    assert impression["section_text"] == impression["original_text"]
    assert undone["verification_status"] == "partially_verified"

    assert api_client.post(f"{url}/impression/decision", json={"decision": "approved"}).status_code == 422
    assert api_client.post(f"{url}/impression/decision", json={"decision": "confirmed", "text": "  "}).status_code == 422
    assert api_client.post(f"{url}/addendum/decision", json={"decision": "confirmed"}).status_code == 404


def test_rejected_section_wording_never_reaches_confirmed_findings(api_client):
    study_id = _study(api_client)
    _upload(api_client, study_id, _pdf([PAGE_ONE, PAGE_TWO]))
    before = api_client.get(f"/api/imaging/studies/{study_id}/findings").json()["findings"]
    assert before and all(f["section"] == "impression" for f in before)
    api_client.post(f"/api/imaging/studies/{study_id}/report/sections/impression/decision", json={"decision": "rejected"})
    after = api_client.get(f"/api/imaging/studies/{study_id}/findings").json()["findings"]
    assert all(f["verification_status"] == "rejected" for f in after)
    api_client.post(f"/api/imaging/studies/{study_id}/report/sections/impression/decision", json={"decision": "unverified"})
    restored = api_client.get(f"/api/imaging/studies/{study_id}/findings").json()["findings"]
    assert all(f["verification_status"] == "unverified" for f in restored)


def test_a_finding_on_the_second_page_points_at_the_second_page(api_client):
    study_id = _study(api_client)
    report = _pdf([["EXAM: CT abdomen", "FINDINGS:", "Normal liver.", "IMPRESSION:", "1. Normal liver."],
                   ["2. Small simple renal cyst."]])
    _upload(api_client, study_id, report)
    findings = api_client.get(f"/api/imaging/studies/{study_id}/findings").json()["findings"]
    pages = {f["original_text"]: f["source_page"] for f in findings}
    assert pages == {"Normal liver.": 1, "Small simple renal cyst.": 2}


def test_boundaries_can_be_corrected_using_only_the_reports_own_lines(api_client):
    study_id = _study(api_client)
    sections = _upload(api_client, study_id, _pdf([PAGE_ONE, PAGE_TWO]))
    lines = api_client.get(f"/api/imaging/studies/{study_id}/report/lines").json()
    assert lines["adjustable"] and lines["lines"][sections["findings"]["line_start"]]["text"] == "FINDINGS:"

    # The reviewer decides the last findings line belongs to the impression.
    ranges = [{"section_type": t, "line_start": s["line_start"], "line_end": s["line_end"]}
              for t, s in sections.items() if t not in {"findings", "impression"}]
    node_line = next(l["index"] for l in lines["lines"] if l["text"].startswith("Small mediastinal"))
    ranges.append({"section_type": "findings", "line_start": sections["findings"]["line_start"], "line_end": node_line - 1})
    ranges.append({"section_type": "impression", "line_start": node_line, "line_end": sections["impression"]["line_end"]})
    adjusted = api_client.put(f"/api/imaging/studies/{study_id}/report/sections/boundaries", json={"sections": ranges})
    assert adjusted.status_code == 200, adjusted.text
    by_type = {s["section_type"]: s for s in adjusted.json()["sections"]}
    assert by_type["findings"]["original_text"].splitlines()[-1] == "No pleural effusion."
    # The heading label inside the new range is dropped; only wording moves.
    assert by_type["impression"]["original_text"].splitlines() == [
        "Small mediastinal lymph node, unchanged.", "Right upper lobe opacity, compatible with pneumonia.",
    ]
    assert by_type["impression"]["boundary_adjusted"] and by_type["impression"]["page_number"] == 2
    assert by_type["findings"]["boundary_adjusted"] and not by_type["exam"]["boundary_adjusted"]

    overlap = [dict(r) for r in ranges]
    overlap[-1]["line_start"] = node_line - 1
    assert api_client.put(f"/api/imaging/studies/{study_id}/report/sections/boundaries", json={"sections": overlap}).status_code == 422
    duplicate = ranges + [{"section_type": "findings", "line_start": 0, "line_end": 0}]
    assert api_client.put(f"/api/imaging/studies/{study_id}/report/sections/boundaries", json={"sections": duplicate}).status_code == 422

    api_client.post(f"/api/imaging/studies/{study_id}/report/sections/exam/decision", json={"decision": "confirmed"})
    locked = api_client.put(f"/api/imaging/studies/{study_id}/report/sections/boundaries", json={"sections": ranges})
    assert locked.status_code == 409


def test_another_account_cannot_review_adjust_or_read_the_report(api_client, other_user_headers):
    study_id = _study(api_client)
    _upload(api_client, study_id, _pdf([PAGE_ONE, PAGE_TWO]))
    base = f"/api/imaging/studies/{study_id}"
    assert api_client.post(f"{base}/report/sections/findings/decision", json={"decision": "confirmed"}, headers=other_user_headers).status_code == 404
    assert api_client.get(f"{base}/report/lines", headers=other_user_headers).status_code == 404
    assert api_client.put(f"{base}/report/sections/boundaries", json={"sections": []}, headers=other_user_headers).status_code == 404
    assert api_client.post(f"{base}/report/details/apply", json={"fields": ["modality"]}, headers=other_user_headers).status_code == 404


def test_a_photographed_report_is_read_by_local_ocr_with_positions(api_client):
    from src.ocr import ocr_available

    if not ocr_available():
        pytest.skip("Tesseract is not installed")
    doc = pymupdf.open()
    page = doc.new_page()
    for index, line in enumerate(["EXAM: Ultrasound of the abdomen", "FINDINGS:", "The liver is normal in size.",
                                  "IMPRESSION:", "Normal abdominal ultrasound."]):
        page.insert_text((72, 90 + index * 24), line, fontsize=14)
    png = page.get_pixmap(dpi=200).tobytes("png")
    doc.close()
    study_id = _study(api_client, modality="ultrasound")
    sections = _upload(api_client, study_id, png, name="report-photo.png", content_type="image/png")
    assert sections["impression"]["original_text"] == "Normal abdominal ultrasound."
    assert sections["findings"]["extraction_method"] == "tesseract_ocr"
    assert sections["findings"]["source_regions"]
