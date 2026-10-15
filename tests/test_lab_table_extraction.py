"""Position-based lab table extraction (Stage F3.1).

Reproduces the field-mapping defects reported from the review screen, e.g.

    "Laboratory Results - 03/15/2026"   -> test "Laboratory Results -", value "03", unit "/15/2026"
    "Glucose 112 H 70 - 99 mg/dL"       -> test "Glucose 112 H 70 -", value "99"
    "Hemoglobin A1c 6.1 H 4.0 - 5.6 %"  -> test "Hemoglobin A1c 6.1 H 4.0 -", value "5.6"

and checks every measurement keeps its name, value, unit, range, flag,
dates and source page/region, with uncertain rows left for human review.
"""

from __future__ import annotations

import pymupdf

from src.document_intelligence import EXTRACTION_VERSION, _extract_native_page_fields

COLUMNS = (72, 230, 290, 330, 440)
HEADER = ("Test", "Result", "Flag", "Reference Range", "Units")


def _table_page(doc, rows, *, heading="Laboratory Results - 03/15/2026", dates="Collected: 03/15/2026   Reported: 03/16/2026",
                header=HEADER, columns=COLUMNS, footer="Page 1 of 1"):
    page = doc.new_page()
    if heading:
        page.insert_text((72, 60), heading, fontsize=14)
    if dates:
        page.insert_text((72, 82), dates, fontsize=10)
    if header:
        for x, text in zip(columns, header):
            page.insert_text((x, 110), text, fontsize=10)
    y = 130
    for row in rows:
        if isinstance(row, str):  # free text line (section heading, note)
            page.insert_text((72, y), row, fontsize=10)
        else:
            for x, text in zip(columns, row):
                if text:
                    page.insert_text((x, y), text, fontsize=10)
        y += 18
    if footer:
        page.insert_text((72, 760), footer, fontsize=8)
    return page


def _fields(page):
    return _extract_native_page_fields(page, page.number + 1)


def _measurements(fields):
    return [f for f in fields if f.status != "not_applicable" and f.label != "Unread line"]


def _summary(fields):
    return [(f.label, f.value, f.unit, f.reference_range, f.flag) for f in _measurements(fields)]


SCREENSHOT_ROWS = [
    ("Glucose", "112", "H", "70 - 99", "mg/dL"),
    ("Hemoglobin A1c", "6.1", "H", "4.0 - 5.6", "%"),
    ("Creatinine", "0.9", "", "0.6 - 1.3", "mg/dL"),
]


def test_screenshot_report_maps_every_column_correctly():
    doc = pymupdf.open()
    fields = _fields(_table_page(doc, SCREENSHOT_ROWS))
    assert _summary(fields) == [
        ("Glucose", "112", "mg/dL", "70 - 99", "H"),
        ("Hemoglobin A1c", "6.1", "%", "4.0 - 5.6", "H"),
        ("Creatinine", "0.9", "mg/dL", "0.6 - 1.3", ""),
    ]
    statuses = {f.label: f.status for f in _measurements(fields)}
    assert statuses == {"Glucose": "flagged_high_on_report", "Hemoglobin A1c": "flagged_high_on_report", "Creatinine": "in_listed_range"}


def test_report_heading_and_footer_are_never_measurements():
    doc = pymupdf.open()
    fields = _fields(_table_page(doc, SCREENSHOT_ROWS))
    labels = [f.label for f in fields]
    assert not any("Laboratory" in label or "Page" in label for label in labels)
    for field in _measurements(fields):
        assert not field.unit.startswith(("/", "-"))
        assert "/" not in field.value and "-" not in field.value


def test_collection_and_report_dates_are_both_kept_and_labelled():
    doc = pymupdf.open()
    fields = _fields(_table_page(doc, SCREENSHOT_ROWS))
    dates = [(f.label, f.value) for f in fields if f.status == "not_applicable"]
    assert dates == [("Collection date", "03/15/2026"), ("Report date", "03/16/2026")]


def test_every_measurement_keeps_its_source_region_text_and_extraction_snapshot():
    doc = pymupdf.open()
    page = _table_page(doc, SCREENSHOT_ROWS)
    for field in _measurements(_fields(page)):
        assert field.page_number == 1
        assert field.label in field.source_text and field.value in field.source_text
        x0, y0, x1, y1 = field.source_bbox
        assert 0 <= x0 < x1 <= page.rect.width and 0 <= y0 < y1 <= page.rect.height
        assert field.extracted == {"label": field.label, "value": field.value, "unit": field.unit, "reference_range": field.reference_range}


def test_missing_reference_range_and_missing_unit_are_left_empty_not_invented():
    doc = pymupdf.open()
    fields = _fields(_table_page(doc, [("Ferritin", "45", "", "", "ng/mL"), ("Specific gravity", "1.020", "", "1.005 - 1.030", "")]))
    assert _summary(fields) == [("Ferritin", "45", "ng/mL", "", ""), ("Specific gravity", "1.020", "", "1.005 - 1.030", "")]


def test_flag_that_contradicts_the_printed_range_goes_to_review():
    doc = pymupdf.open()
    fields = _fields(_table_page(doc, [("Glucose", "85", "H", "70 - 99", "mg/dL")]))
    (glucose,) = _measurements(fields)
    assert glucose.flag == "H"
    assert glucose.confidence == "needs_review"


def test_flag_printed_inside_the_result_cell_is_split_off():
    doc = pymupdf.open()
    fields = _fields(_table_page(doc, [("Potassium", "5.9H", "", "3.5 - 5.1", "mmol/L")]))
    assert _summary(fields) == [("Potassium", "5.9", "mmol/L", "3.5 - 5.1", "H")]


def test_multi_line_test_name_is_joined_and_section_headings_are_skipped():
    doc = pymupdf.open()
    rows = [
        "Complete Blood Count",
        ("Mean corpuscular", "", "", "", ""),
        ("", "88", "", "80 - 100", "fL"),
        ("Platelets", "250", "", "150 - 400", "10^3/uL"),
    ]
    fields = _fields(_table_page(doc, rows))
    assert _summary(fields) == [
        ("Mean corpuscular", "88", "fL", "80 - 100", ""),
        ("Platelets", "250", "10^3/uL", "150 - 400", ""),
    ]


def test_repeated_test_on_one_page_is_kept_as_separate_results():
    doc = pymupdf.open()
    fields = _fields(_table_page(doc, [("Glucose", "112", "H", "70 - 99", "mg/dL"), ("Glucose", "96", "", "70 - 99", "mg/dL")]))
    assert [(f.label, f.value) for f in _measurements(fields)] == [("Glucose", "112"), ("Glucose", "96")]


def test_different_column_order_is_read_from_the_header():
    doc = pymupdf.open()
    header = ("Analyte", "Units", "Value", "Normal Range", "Flag")
    rows = [("Sodium", "mmol/L", "128", "136 - 145", "L")]
    fields = _fields(_table_page(doc, rows, header=header))
    assert _summary(fields) == [("Sodium", "128", "mmol/L", "136 - 145", "L")]
    assert _measurements(fields)[0].status == "flagged_low_on_report"


def test_table_without_a_header_falls_back_to_the_strict_line_grammar():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Laboratory Results - 03/15/2026", fontsize=12)
    page.insert_text((72, 100), "Glucose 112 H 70 - 99 mg/dL", fontsize=10)
    page.insert_text((72, 118), "Hemoglobin A1c 6.1 H 4.0 - 5.6 %", fontsize=10)
    fields = _fields(page)
    assert _summary(fields) == [
        ("Glucose", "112", "mg/dL", "70 - 99", "H"),
        ("Hemoglobin A1c", "6.1", "%", "4.0 - 5.6", "H"),
    ]


def test_garbled_result_row_is_flagged_never_guessed():
    doc = pymupdf.open()
    fields = _fields(_table_page(doc, [("Gluc0se", "1l2", "", "70 - 99", "mg/dL")]))
    (row,) = [f for f in fields if f.status != "not_applicable"]
    assert row.confidence in {"needs_review", "could_not_read"}


def test_multi_page_report_keeps_each_page_its_own_values_and_dates(api_client):
    doc = pymupdf.open()
    _table_page(doc, [("Glucose", "112", "H", "70 - 99", "mg/dL")], dates="Collected: 03/15/2026")
    _table_page(doc, [("Glucose", "101", "H", "70 - 99", "mg/dL")], heading="Laboratory Results - 06/20/2026", dates="Collected: 06/20/2026")
    uploaded = api_client.post("/api/documents/v2/upload", files={"file": ("labs.pdf", doc.tobytes(), "application/pdf")}).json()
    state = api_client.post(f"/api/documents/v2/{uploaded['document_id']}/process").json()
    assert state["extraction_version"] == EXTRACTION_VERSION
    assert [p["width"] > 0 for p in state["pages"]] == [True, True]
    by_page = {(f["page_number"], f["label"]): f["value"] for f in state["fields"]}
    assert by_page[(1, "Glucose")] == "112" and by_page[(1, "Collection date")] == "03/15/2026"
    assert by_page[(2, "Glucose")] == "101" and by_page[(2, "Collection date")] == "06/20/2026"

    confirm = api_client.post(
        f"/api/documents/v2/{uploaded['document_id']}/confirm",
        json={"fields": state["fields"], "reviewed_names_values_units_dates": True},
    )
    assert confirm.status_code == 200
    points = api_client.get("/api/labs/timeline/glucose").json()["points"]
    assert sorted((p["collection_date"], p["value"], p.get("page_number")) for p in points) == [
        ("2026-03-15", 112.0, 1),
        ("2026-06-20", 101.0, 2),
    ]


def test_collection_date_wins_over_report_date_on_the_timeline(api_client):
    doc = pymupdf.open()
    _table_page(doc, SCREENSHOT_ROWS)
    uploaded = api_client.post("/api/documents/v2/upload", files={"file": ("labs.pdf", doc.tobytes(), "application/pdf")}).json()
    state = api_client.post(f"/api/documents/v2/{uploaded['document_id']}/process").json()
    api_client.post(
        f"/api/documents/v2/{uploaded['document_id']}/confirm",
        json={"fields": state["fields"], "reviewed_names_values_units_dates": True},
    )
    (point,) = api_client.get("/api/labs/timeline/glucose").json()["points"]
    assert point["collection_date"] == "2026-03-15"


def test_reextract_rereads_an_unconfirmed_pdf_and_refuses_a_confirmed_one(api_client):
    doc = pymupdf.open()
    _table_page(doc, SCREENSHOT_ROWS)
    uploaded = api_client.post("/api/documents/v2/upload", files={"file": ("labs.pdf", doc.tobytes(), "application/pdf")}).json()
    document_id = uploaded["document_id"]
    first = api_client.post(f"/api/documents/v2/{document_id}/process").json()

    again = api_client.post(f"/api/documents/v2/{document_id}/reextract")
    assert again.status_code == 200
    assert [f["value"] for f in again.json()["fields"]] == [f["value"] for f in first["fields"]]

    api_client.post(
        f"/api/documents/v2/{document_id}/confirm",
        json={"fields": again.json()["fields"], "reviewed_names_values_units_dates": True},
    )
    refused = api_client.post(f"/api/documents/v2/{document_id}/reextract")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "DOCUMENT_ALREADY_CONFIRMED"
    assert api_client.get("/api/labs/timeline/glucose").json()["count"] == 1


def test_review_edit_keeps_the_original_extraction_snapshot(api_client):
    doc = pymupdf.open()
    _table_page(doc, SCREENSHOT_ROWS)
    uploaded = api_client.post("/api/documents/v2/upload", files={"file": ("labs.pdf", doc.tobytes(), "application/pdf")}).json()
    state = api_client.post(f"/api/documents/v2/{uploaded['document_id']}/process").json()
    edited = [{**f, "value": "113"} if f["label"] == "Glucose" else f for f in state["fields"]]
    saved = api_client.post(
        f"/api/documents/v2/{uploaded['document_id']}/confirm",
        json={"fields": edited, "reviewed_names_values_units_dates": True},
    ).json()
    glucose = next(f for f in saved["fields"] if f["label"] == "Glucose")
    assert glucose["value"] == "113" and glucose["user_edited"] is True
    assert glucose["extracted"]["value"] == "112"
