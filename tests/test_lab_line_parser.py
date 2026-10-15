"""The strict lab-line parser never maps report metadata into measurements.

Each "not a measurement" case below reproduces a real mis-mapping from the
previous parser (shown in the comment), so a regression is caught by name.
"""

from __future__ import annotations

import pytest

from src.labs.line_parser import (
    check_extracted_measurement,
    find_result_date,
    is_unparsed_result_line,
    looks_like_date,
    parse_lab_line,
)


@pytest.mark.parametrize(
    "line",
    [
        "Specimen collected: 01/15/2026",  # was value "01", unit "/15/2026"
        "Printed 2026-01-15",              # was value "2026", unit "-01-15"
        "Received: 2026-01-16 08:30",      # was value "2026", unit "-01-16"
        "Reference range: 4.0-11.0",       # was value "4.0", unit "-11"
        "Normal range 70-99",              # was value "70", unit "-99"
        "Age: 45 yrs",                     # was a measurement "Age 45 yrs"
        "Phone: 555-0100",                 # was value "555", unit "-0100"
        "Fasting 12 hours",                # was a measurement "Fasting 12 hours"
        "Lab Report Page 1 of 3",
        "Visit 2 of 3",
        "Synthetic Longitudinal Lab Report",
        "Test Value Unit Reference range",
        "Collection date: 2026-01-15",
    ],
)
def test_metadata_headings_dates_and_range_fragments_are_not_measurements(line):
    assert parse_lab_line(line) is None


@pytest.mark.parametrize(
    "line, label, value, unit, reference_range",
    [
        ("Hemoglobin A1C 6.2 % Ref <5.7", "Hemoglobin A1C", "6.2", "%", "<5.7"),
        ("WBC 6.1 10^3/uL Ref 4.0-11.0", "WBC", "6.1", "10^3/uL", "4.0-11.0"),
        ("Platelets 238 10^3/uL Ref 150-400", "Platelets", "238", "10^3/uL", "150-400"),
        ("Glucose: 98 mg/dL (70-99)", "Glucose", "98", "mg/dL", "70-99"),
        ("Hemoglobin 13.2 g/dL 12.0 - 15.5", "Hemoglobin", "13.2", "g/dL", "12.0 - 15.5"),
        ("Creatinine 1.10 mg/dL [0.60-1.30]", "Creatinine", "1.10", "mg/dL", "0.60-1.30"),
        ("TSH 2.1 mIU/L 0.4 to 4.0", "TSH", "2.1", "mIU/L", "0.4 to 4.0"),
        ("WBC 6.4 10^3/uL", "WBC", "6.4", "10^3/uL", ""),
        ("eGFR >90 mL/min/1.73m2", "eGFR", ">90", "mL/min/1.73m2", ""),
        ("Vitamin D 25-OH 32 ng/mL 30-100", "Vitamin D 25-OH", "32", "ng/mL", "30-100"),
    ],
)
def test_measurement_rows_keep_name_value_unit_and_range_exactly_as_printed(line, label, value, unit, reference_range):
    parsed = parse_lab_line(line)
    assert parsed is not None
    assert (parsed.label, parsed.value, parsed.unit, parsed.reference_range) == (label, value, unit, reference_range)
    assert parsed.needs_review is False
    assert parsed.source_text == line


@pytest.mark.parametrize(
    "line, flag",
    [
        # was a test named "Glucose 101 H mg/dL Ref" with value "70"
        ("Glucose 101 H mg/dL Ref 70-99", "H"),
        ("Glucose 101 mg/dL H Ref 70-99", "H"),
        ("Potassium 5.6 HH mmol/L 3.5-5.1", "HH"),
    ],
)
def test_printed_high_low_flags_are_separated_from_name_and_unit(line, flag):
    parsed = parse_lab_line(line)
    assert parsed is not None
    assert parsed.flag == flag
    assert parsed.unit in {"mg/dL", "mmol/L"}
    assert parsed.label in {"Glucose", "Potassium"}


def test_unexplained_trailing_text_is_kept_but_flagged_for_review():
    parsed = parse_lab_line("LDL Cholesterol 130 mg/dL <100 borderline")
    assert parsed is not None
    assert (parsed.label, parsed.value, parsed.unit, parsed.reference_range) == ("LDL Cholesterol", "130", "mg/dL", "<100")
    assert parsed.needs_review is True


@pytest.mark.parametrize("line", ["Glucose 96 mg/dL 70-99 12", "Neutrophils % 55 40-75"])
def test_ambiguous_result_rows_are_surfaced_not_guessed(line):
    assert parse_lab_line(line) is None
    assert is_unparsed_result_line(line) is True


@pytest.mark.parametrize("line", ["Lab Report Page 1 of 3", "Specimen collected: 01/15/2026", "Educational sample only"])
def test_metadata_is_never_surfaced_as_an_unread_result(line):
    assert is_unparsed_result_line(line) is False


def test_collection_date_is_labelled_as_collection_date_and_preferred_over_report_date():
    found = find_result_date("Report date: 2026-01-20\nCollection date: 2026-01-15")
    assert found is not None
    assert (found.label, found.value) == ("Collection date", "2026-01-15")


def test_report_date_is_used_and_labelled_only_when_no_collection_date_is_printed():
    found = find_result_date("Reported 01/20/2026")
    assert found is not None
    assert (found.label, found.value) == ("Report date", "01/20/2026")


@pytest.mark.parametrize(
    "label, value, unit, verdict",
    [
        ("Glucose", "96", "mg/dL", "ok"),
        ("Reference range", "4.0", "-11", "reject"),
        ("Specimen collected", "01", "/15/2026", "reject"),
        ("Patient age", "45", "yrs", "reject"),
        ("Printed", "2026-01-15", "", "reject"),
        ("Urine protein", "Negative", "", "review"),
    ],
)
def test_model_proposed_measurements_are_checked_the_same_way(label, value, unit, verdict):
    assert check_extracted_measurement(label, value, unit) == verdict


@pytest.mark.parametrize("value, expected", [("2026-01-15", True), ("01/15/2026", True), ("4.0-11.0", False), ("08:30", False)])
def test_ranges_and_times_are_not_dates(value, expected):
    assert looks_like_date(value) is expected


# ---- Stage F3.1: rows from the reported review-screen defects ------------

@pytest.mark.parametrize(
    "line, expected",
    [
        # was test "Glucose 112 H 70 -" with value "99"
        ("Glucose 112 H 70 - 99 mg/dL", ("Glucose", "112", "mg/dL", "70 - 99", "H")),
        # was test "Hemoglobin A1c 6.1 H 4.0 -" with value "5.6"
        ("Hemoglobin A1c 6.1 H 4.0 - 5.6 %", ("Hemoglobin A1c", "6.1", "%", "4.0 - 5.6", "H")),
        ("Creatinine 0.9 0.6 - 1.3 mg/dL", ("Creatinine", "0.9", "mg/dL", "0.6 - 1.3", "")),
        ("WBC 6.1 4.0 - 11.0 10^3/uL", ("WBC", "6.1", "10^3/uL", "4.0 - 11.0", "")),
        ("LDL Cholesterol 142 H <100 mg/dL", ("LDL Cholesterol", "142", "mg/dL", "<100", "H")),
    ],
)
def test_unit_printed_after_the_reference_range_is_attached(line, expected):
    parsed = parse_lab_line(line)
    assert parsed is not None
    assert (parsed.label, parsed.value, parsed.unit, parsed.reference_range, parsed.flag) == expected
    assert parsed.needs_review is False


def test_report_heading_with_a_date_is_not_a_measurement():
    # was test "Laboratory Results -", value "03", unit "/15/2026"
    assert parse_lab_line("Laboratory Results - 03/15/2026") is None


def test_a_value_never_ends_mid_number():
    # "70 - 99" must not become value "7" with range "0 - 99"
    assert parse_lab_line("Gluc0se 1l2 70 - 99 mg/dL") is None


def test_two_units_on_one_row_are_flagged_not_chosen():
    parsed = parse_lab_line("Glucose 96 mg/dL 70-99 mg/dL")
    assert parsed is not None and parsed.needs_review is True


def test_a_name_with_a_free_standing_number_is_rejected():
    assert parse_lab_line("Glucose 112 70 mg/dL") is None


@pytest.mark.parametrize(
    "line, label",
    [
        # Was dropped as metadata because the label starts with "Fasting".
        ("Fasting Glucose 95 mg/dL Ref 70-99", "Fasting Glucose"),
        # Was dropped as metadata because the label starts with "Sex".
        ("Sex Hormone Binding Globulin 45 nmol/L 18-144", "Sex Hormone Binding Globulin"),
        # Was dropped because "Tel" matched without a word boundary.
        ("Telopeptide 300 pg/mL", "Telopeptide"),
    ],
)
def test_test_names_that_start_like_metadata_are_still_results(line, label):
    parsed = parse_lab_line(line)
    assert parsed is not None and parsed.label == label


@pytest.mark.parametrize("line", ["Fasting: Yes", "Fasting 12 hours", "Fasting status: no", "Sex: F", "Tel: 555 1234"])
def test_fasting_and_contact_metadata_are_still_not_results(line):
    assert parse_lab_line(line) is None
