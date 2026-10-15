from __future__ import annotations

from src.imaging_sections import split_report_sections


def test_splits_clean_headers():
    text = (
        "EXAM: MRI Right Knee\n"
        "CLINICAL HISTORY: Right knee pain.\n"
        "TECHNIQUE: Standard MRI protocol without contrast.\n"
        "FINDINGS: There is a small joint effusion. No acute fracture is seen.\n"
        "IMPRESSION: Small joint effusion. No acute fracture.\n"
    )
    sections = split_report_sections(text)
    assert sections["exam"] == "MRI Right Knee"
    assert sections["clinical_history"] == "Right knee pain."
    assert sections["technique"] == "Standard MRI protocol without contrast."
    assert sections["findings"] == "There is a small joint effusion. No acute fracture is seen."
    assert sections["impression"] == "Small joint effusion. No acute fracture."


def test_header_and_content_on_same_line():
    text = "FINDINGS: No acute abnormality.\nIMPRESSION: Normal study."
    sections = split_report_sections(text)
    assert sections["findings"] == "No acute abnormality."
    assert sections["impression"] == "Normal study."


def test_header_without_colon():
    text = "FINDINGS\nNo acute abnormality.\n\nIMPRESSION\nNormal study."
    sections = split_report_sections(text)
    assert sections["findings"] == "No acute abnormality."
    assert sections["impression"] == "Normal study."


def test_conclusion_maps_to_impression():
    text = "FINDINGS: Normal.\nCONCLUSION: No acute disease."
    sections = split_report_sections(text)
    assert sections["impression"] == "No acute disease."


def test_unknown_headers_return_empty_rather_than_guessing():
    text = "Patient presented for evaluation. Everything looked fine to the technician."
    assert split_report_sections(text) == {}


def test_empty_text_returns_empty():
    assert split_report_sections("") == {}
    assert split_report_sections("   \n  ") == {}


def test_repeated_header_keeps_both_passages_in_order():
    """A section header appearing twice (e.g. an addendum) keeps both
    passages, first one first. The previous behaviour kept only the first
    and silently dropped the radiologist's later wording."""
    text = "FINDINGS: First set of findings.\nFINDINGS: Addendum findings."
    sections = split_report_sections(text)
    assert sections["findings"] == "First set of findings.\n\nAddendum findings."
