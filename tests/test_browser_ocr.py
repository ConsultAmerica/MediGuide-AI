"""OCR done in the browser (tesseract.js) for deployments without Tesseract.

The browser sends its words with the upload as ``client_ocr``; the server
uses them in place of its own OCR, scaled onto the page image, and the
extraction pipeline is unchanged. Here the words come from the PDF the
photo was rendered from, standing in for what the browser would read.
"""

from __future__ import annotations

import io
import json

import pymupdf
import pytest
from PIL import Image

import src.document_intelligence as di
import src.ocr as ocr

ROWS = [("Glucose", "112", "H", "70 - 99", "mg/dL"), ("Creatinine", "0.9", "", "0.6 - 1.3", "mg/dL")]


@pytest.fixture(autouse=True)
def no_server_ocr_or_vision(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_path", lambda: None)
    monkeypatch.setattr(di, "_extract_page_fields", lambda *args, **kwargs: [])


def _report() -> tuple[bytes, list[dict], float, float]:
    """A photo-like PNG of a lab report and the words on it (PDF points)."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Laboratory Results - 03/15/2026", fontsize=14)
    cols = (72, 230, 290, 330, 440)
    for x, text in zip(cols, ("Test", "Result", "Flag", "Reference Range", "Units")):
        page.insert_text((x, 110), text, fontsize=10)
    for i, row in enumerate(ROWS):
        for x, text in zip(cols, row):
            if text:
                page.insert_text((x, 130 + i * 18), text, fontsize=10)
    words = [
        {"x0": w[0], "y0": w[1], "x1": w[2], "y1": w[3], "text": w[4], "confidence": 93}
        for w in page.get_text("words")
    ]
    pix = page.get_pixmap(dpi=200)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), words, page.rect.width, page.rect.height


def _process(client, data: bytes, client_ocr: str | None) -> dict:
    form = {"client_ocr": client_ocr} if client_ocr is not None else {}
    uploaded = client.post(
        "/api/documents/v2/upload", files={"file": ("labs.png", data, "image/png")}, data=form
    ).json()
    return client.post(f"/api/documents/v2/{uploaded['document_id']}/process").json()


def test_photo_is_read_from_browser_ocr_when_the_server_has_none(api_client):
    data, words, width, height = _report()
    client_ocr = json.dumps([{"page": 1, "width": width, "height": height, "words": words}])

    state = _process(api_client, data, client_ocr)

    assert state["status"] == "review_required", state
    found = {(f["label"], f["value"], f["unit"]) for f in state["fields"] if f["status"] != "not_applicable"}
    assert ("Glucose", "112", "mg/dL") in found
    assert ("Creatinine", "0.9", "mg/dL") in found
    assert state["pages"][0]["text_source"] == "ocr"
    # Positions are mapped from the browser's coordinates onto the page image.
    glucose = next(f for f in state["fields"] if f["label"] == "Glucose")
    assert glucose["source_bbox"] and glucose["source_bbox"][0] > 100


def test_malformed_browser_ocr_is_ignored_not_trusted(api_client):
    data, _words, _width, _height = _report()

    state = _process(api_client, data, "not json")

    assert not [f for f in state["fields"] if f["status"] != "not_applicable"]


def test_clean_client_pages_drops_bad_entries():
    pages = ocr._clean_client_pages([
        {"page": 1, "width": 100, "height": 100, "words": [
            {"x0": 1, "y0": 1, "x1": 5, "y1": 5, "text": "ok", "confidence": 250},
            {"x0": 5, "y0": 5, "x1": 1, "y1": 1, "text": "inverted"},
            {"text": "no box"},
        ]},
        {"page": 0, "width": 100, "height": 100, "words": []},
        "junk",
    ])
    assert list(pages) == [1]
    assert pages[1]["words"] == [[1.0, 1.0, 5.0, 5.0, "ok", 100.0]]
