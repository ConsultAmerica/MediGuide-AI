"""Medication label extraction has no ProcessingJob row (see the model
docstring on MedicationRecord and the scoping note in
src/medication_workspace.py's _call_with_classification) — so unlike
documents/imaging, this only covers request-scoped retry/classification,
not durable job state. That's the deliberately smaller scope agreed for
this feature: fix the actual reported bug (a raw exception name leaking
through with no retry) without a bigger schema change.
"""

from __future__ import annotations

import pymupdf
import pytest
from ollama import ResponseError


def _make_label_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeResponse:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


_VALID_LABEL_JSON = (
    '{"medication_name": {"value": "Amoxicillin", "confidence": "clearly_visible", "source_text": ""}, '
    '"strength": {"value": "500mg", "confidence": "clearly_visible", "source_text": ""}, '
    '"form": {"value": "", "confidence": "could_not_read", "source_text": ""}, '
    '"instructions": {"value": "", "confidence": "could_not_read", "source_text": ""}, '
    '"quantity": {"value": "", "confidence": "could_not_read", "source_text": ""}, '
    '"prescriber_or_pharmacy": {"value": "", "confidence": "could_not_read", "source_text": ""}, '
    '"other_visible_text": ""}'
)


class _FakeClient:
    """Stands in for ollama.Client — .chat() raises `errors` in order, then
    returns a valid extraction response once exhausted."""

    def __init__(self, errors: list[Exception]):
        self._errors = list(errors)
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return _FakeResponse(_VALID_LABEL_JSON)


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    """Real backoff (2s/5s) would make these tests slow for no reason —
    the timing itself is already covered by tests/test_resilience.py."""
    import src.medication_workspace as medication_workspace

    monkeypatch.setattr(medication_workspace, "PROCESSING_RETRY_BACKOFF_SCHEDULE_SECONDS", (0, 0))
    # Pinned rather than read from the env default (which dropped from 3 to
    # 2), so "two transient failures, then success" stays reachable.
    monkeypatch.setattr(medication_workspace, "PROCESSING_RETRY_ATTEMPTS", 3)


def test_transient_failure_retries_then_succeeds(api_client, monkeypatch):
    import src.medication_workspace as medication_workspace

    fake_client = _FakeClient([ConnectionError("refused"), ConnectionError("refused")])
    monkeypatch.setattr(medication_workspace, "_ollama_client", lambda: fake_client)

    response = api_client.post(
        "/api/medications/v2/upload",
        files={"file": ("label.pdf", _make_label_pdf(), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    by_key = {f["key"]: f["value"] for f in body["fields"]}
    assert by_key["medication_name"] == "Amoxicillin"
    assert fake_client.calls == 3


def test_transient_failure_exhausted_returns_standardized_retryable_error(api_client, monkeypatch):
    import src.medication_workspace as medication_workspace

    fake_client = _FakeClient([ConnectionError("refused")] * 5)
    monkeypatch.setattr(medication_workspace, "_ollama_client", lambda: fake_client)

    response = api_client.post(
        "/api/medications/v2/upload",
        files={"file": ("label.pdf", _make_label_pdf(), "application/pdf")},
    )

    assert response.status_code == 503
    envelope = response.json()["error"]
    assert envelope["code"] == "AI_SERVICE_TEMPORARILY_UNAVAILABLE"
    assert envelope["retryable"] is True
    assert envelope["stage"] == "extracting"
    # The raw exception type is never in the message the client sees.
    assert "ConnectionError" not in envelope["message"]


def test_ollama_5xx_response_error_is_also_treated_as_transient(api_client, monkeypatch):
    import src.medication_workspace as medication_workspace

    fake_client = _FakeClient([ResponseError("model loading", 503)])
    monkeypatch.setattr(medication_workspace, "_ollama_client", lambda: fake_client)

    response = api_client.post(
        "/api/medications/v2/upload",
        files={"file": ("label.pdf", _make_label_pdf(), "application/pdf")},
    )

    assert response.status_code == 200
    assert fake_client.calls == 2


def test_permanent_failure_does_not_retry(api_client, monkeypatch):
    import src.medication_workspace as medication_workspace

    fake_client = _FakeClient([ValueError("garbage response, not JSON")])
    monkeypatch.setattr(medication_workspace, "_ollama_client", lambda: fake_client)

    response = api_client.post(
        "/api/medications/v2/upload",
        files={"file": ("label.pdf", _make_label_pdf(), "application/pdf")},
    )

    assert response.status_code == 422
    envelope = response.json()["error"]
    assert envelope["code"] == "MEDICATION_LABEL_EXTRACTION_FAILED"
    assert envelope["retryable"] is False
    assert fake_client.calls == 1


def test_typed_text_path_gets_the_same_classification(api_client, monkeypatch):
    import src.medication_workspace as medication_workspace

    fake_client = _FakeClient([ConnectionError("refused")] * 5)
    monkeypatch.setattr(medication_workspace, "_ollama_client", lambda: fake_client)

    response = api_client.post(
        "/api/medications/v2/text",
        json={"text": "Amoxicillin 500mg — take one tablet twice daily"},
    )

    assert response.status_code == 503
    envelope = response.json()["error"]
    assert envelope["code"] == "AI_SERVICE_TEMPORARILY_UNAVAILABLE"
    assert envelope["retryable"] is True
