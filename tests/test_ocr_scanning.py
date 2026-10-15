"""Scanned documents and photos (Stage F3.2).

Scanned pages and photos are read with local Tesseract OCR before the AI
vision model is ever tried. Pages carry how they were read and how readable
they were; OCR'd values with uncertain characters go to review; the original
upload is kept; duplicates and concurrent processing are handled safely.

The AI vision fallback is stubbed out so these tests never call a model.
"""

from __future__ import annotations

import io
import threading

import pymupdf
import pytest
from PIL import Image, ImageOps

import src.document_intelligence as di
from src.document_intelligence import _fields_from_rows, _text_layer_usable
from src.labs.table_reader import Row, Word
from src.ocr import ocr_available

needs_tesseract = pytest.mark.skipif(not ocr_available(), reason="Tesseract OCR is not installed")

ROWS = [("Glucose", "112", "H", "70 - 99", "mg/dL"), ("Creatinine", "0.9", "", "0.6 - 1.3", "mg/dL"), ("Sodium", "139", "", "136 - 145", "mmol/L")]
EXPECTED = [("Glucose", "112", "mg/dL", "70-99"), ("Creatinine", "0.9", "mg/dL", "0.6-1.3"), ("Sodium", "139", "mmol/L", "136-145")]


@pytest.fixture(autouse=True)
def no_vision_model(monkeypatch):
    monkeypatch.setattr(di, "_extract_page_fields", lambda *args, **kwargs: [])


def _report_image(dpi: int = 200) -> Image.Image:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Laboratory Results - 03/15/2026", fontsize=14)
    page.insert_text((72, 82), "Collected: 03/15/2026", fontsize=10)
    cols = (72, 230, 290, 330, 440)
    for x, text in zip(cols, ("Test", "Result", "Flag", "Reference Range", "Units")):
        page.insert_text((x, 110), text, fontsize=10)
    for i, row in enumerate(ROWS):
        for x, text in zip(cols, row):
            if text:
                page.insert_text((x, 130 + i * 18), text, fontsize=10)
    pix = page.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _scanned_pdf(image: Image.Image) -> bytes:
    """An image-only PDF, like a scanner produces: no text layer at all."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_image(page.rect, stream=buffer.getvalue())
    return doc.tobytes()


def _upload(client, name: str, data: bytes, content_type: str) -> dict:
    uploaded = client.post("/api/documents/v2/upload", files={"file": (name, data, content_type)}).json()
    state = client.post(f"/api/documents/v2/{uploaded['document_id']}/process").json()
    assert state["status"] == "review_required", state
    return state


def _summary(state):
    # OCR spacing around a dash varies ("0.6-1.3" vs "0.6 - 1.3"); the
    # printed range is the same, so compare it with spaces removed.
    return [
        (f["label"], f["value"], f["unit"], f["reference_range"].replace(" ", ""))
        for f in state["fields"] if f["status"] != "not_applicable"
    ]


def _jpeg(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


@needs_tesseract
def test_scanned_pdf_is_read_by_local_ocr_with_positions_and_quality(api_client):
    state = _upload(api_client, "scan.pdf", _scanned_pdf(_report_image()), "application/pdf")
    assert _summary(state) == EXPECTED
    page = state["pages"][0]
    assert page["text_source"] == "ocr" and page["quality"] in {"good", "fair"}
    assert page["ocr_confidence"] and page["ocr_confidence"] > 70
    for field in state["fields"]:
        assert field["extraction_method"] == "tesseract_ocr"
        if field["source_bbox"]:
            x0, y0, x1, y1 = field["source_bbox"]
            assert 0 <= x0 < x1 <= page["width"] and 0 <= y0 < y1 <= page["height"]
    assert [(f["label"], f["value"]) for f in state["fields"] if f["status"] == "not_applicable"] == [("Collection date", "03/15/2026")]


@needs_tesseract
def test_phone_photo_jpeg_is_read(api_client):
    state = _upload(api_client, "photo.jpg", _jpeg(_report_image()), "image/jpeg")
    assert _summary(state) == EXPECTED
    assert state["pages"][0]["text_source"] == "ocr"


@needs_tesseract
def test_rotated_photo_is_turned_upright_before_reading(api_client):
    rotated = _report_image().rotate(90, expand=True)  # sideways, as a phone often captures
    state = _upload(api_client, "sideways.jpg", _jpeg(rotated), "image/jpeg")
    assert _summary(state) == EXPECTED
    page = state["pages"][0]
    assert any(note.startswith("Rotated") for note in page["quality_notes"])
    assert page["width"] > page["height"] or page["height"] > page["width"]  # upright page coordinate space


@needs_tesseract
def test_low_contrast_scan_is_normalised_and_noted(api_client):
    faded = ImageOps.grayscale(_report_image()).point(lambda v: 150 + v * 60 // 255)
    state = _upload(api_client, "faded.jpg", _jpeg(faded), "image/jpeg")
    assert "Low contrast" in state["pages"][0]["quality_notes"]
    assert _summary(state) == EXPECTED


@needs_tesseract
def test_low_resolution_photo_is_flagged_and_asks_for_a_better_capture(api_client):
    small = _report_image(dpi=200).resize((800, 1035))
    state = _upload(api_client, "small.jpg", _jpeg(small), "image/jpeg")
    notes = state["pages"][0]["quality_notes"]
    assert "Low resolution" in notes and "A closer, sharper photo will read more reliably" in notes


@needs_tesseract
def test_blank_page_is_reported_unreadable_with_no_invented_values(api_client):
    blank = Image.new("RGB", (1600, 2000), "white")
    state = _upload(api_client, "blank.jpg", _jpeg(blank), "image/jpeg")
    page = state["pages"][0]
    assert state["fields"] == []
    assert page["quality"] == "unreadable" and "No readable text found" in page["quality_notes"]


def test_text_pdf_is_read_from_its_text_layer_and_never_ocrd(api_client, monkeypatch):
    def _no_ocr(*args, **kwargs):
        raise AssertionError("a good text layer must not be OCR'd")

    monkeypatch.setattr(di, "ocr_image", _no_ocr)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Collection date: 2026-02-01\nGlucose 96 mg/dL Ref 70-99\nSodium 139 mmol/L Ref 136-145", fontsize=10)
    state = _upload(api_client, "text.pdf", doc.tobytes(), "application/pdf")
    assert state["pages"][0]["text_source"] == "text_layer"
    assert {f["extraction_method"] for f in state["fields"]} == {"native_text"}


def test_garbled_text_layer_is_not_trusted():
    assert _text_layer_usable("Glucose 96 mg/dL Ref 70-99 Sodium 139 mmol/L") is True
    assert _text_layer_usable("��� �� ���� ��� glucose") is False
    assert _text_layer_usable("") is False


def test_low_confidence_ocr_words_send_the_row_to_review():
    def row(confidence):
        words = [("Glucose", 72), ("112", 230), ("70", 330), ("-", 345), ("99", 352), ("mg/dL", 440)]
        return Row([Word(x, 100, x + 30, 110, text, 99.0 if text != "112" else confidence) for text, x in words])

    clear = _fields_from_rows([row(96.0)], "", 1, method="tesseract_ocr")
    unsure = _fields_from_rows([row(55.0)], "", 1, method="tesseract_ocr")
    assert clear[0].confidence == "clearly_visible"
    assert unsure[0].confidence == "needs_review"
    assert unsure[0].value == "112"  # flagged, never changed


@needs_tesseract
def test_original_photo_is_kept_and_photos_can_be_re_read(api_client):
    data = _jpeg(_report_image())
    state = _upload(api_client, "keep.jpg", data, "image/jpeg")
    original = next((di._folder(state["document_id"]) / "pages").glob("upload.*"))
    assert original.read_bytes() == data
    again = api_client.post(f"/api/documents/v2/{state['document_id']}/reextract")
    assert again.status_code == 200
    assert _summary(again.json()) == EXPECTED


def test_reuploading_a_confirmed_document_is_flagged_as_a_duplicate(api_client):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Collection date: 2026-02-01\nGlucose 96 mg/dL Ref 70-99", fontsize=10)
    data = doc.tobytes()
    first = _upload(api_client, "labs.pdf", data, "application/pdf")
    assert first["duplicate_of"] is None
    api_client.post(f"/api/documents/v2/{first['document_id']}/confirm",
                    json={"fields": first["fields"], "reviewed_names_values_units_dates": True})
    second = _upload(api_client, "labs-again.pdf", data, "application/pdf")
    assert second["duplicate_of"] == {"document_id": first["document_id"], "filename": "labs.pdf"}
    assert second["content_sha256"] == first["content_sha256"]


def test_concurrent_processing_requests_run_one_extraction(api_client, monkeypatch):
    calls = []
    real = di._process_saved_pdf

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(di, "_process_saved_pdf", counting)
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Collection date: 2026-02-01\nGlucose 96 mg/dL Ref 70-99", fontsize=10)
    uploaded = api_client.post("/api/documents/v2/upload", files={"file": ("labs.pdf", doc.tobytes(), "application/pdf")}).json()

    results = []

    def process():
        results.append(api_client.post(f"/api/documents/v2/{uploaded['document_id']}/process").json())

    threads = [threading.Thread(target=process) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(calls) == 1
    assert all(r["status"] == "review_required" for r in results)
    assert len({tuple(f["field_id"] for f in r["fields"]) for r in results}) == 1


def test_several_numbers_in_one_value_cell_are_never_joined_into_a_value():
    from src.labs.table_reader import measurement_from_cells

    merged = {"name": "Glucose Creatinine Sodium", "value": "0.9 2 139", "range": "", "unit": ""}
    assert measurement_from_cells(merged, "Glucose Creatinine Sodium 0.9 2 139") is None
    comparator = {"name": "Troponin", "value": "< 0.01", "range": "", "unit": "ng/mL"}
    parsed = measurement_from_cells(comparator, "Troponin < 0.01 ng/mL")
    assert parsed is not None and parsed.value == "<0.01"


@needs_tesseract
def test_vision_model_fallback_values_always_need_review(api_client, monkeypatch):
    from src.document_intelligence import ExtractedField

    def vision(*args, **kwargs):
        return [ExtractedField(field_id="v1", label="Glucose", value="112", unit="mg/dL", reference_range="70-99",
                               status="unknown", confidence="clearly_visible", page_number=1, extraction_method="vision_ocr")]

    monkeypatch.setattr(di, "_extract_page_fields", vision)
    blank = Image.new("RGB", (1600, 2000), "white")
    state = _upload(api_client, "unreadable.jpg", _jpeg(blank), "image/jpeg")
    (field,) = state["fields"]
    assert field["confidence"] == "needs_review" and field["source_bbox"] is None
    notes = state["pages"][0]["quality_notes"]
    assert state["pages"][0]["text_source"] == "vision"
    assert "OCR could not read this page" in notes and "No readable text found" not in notes
