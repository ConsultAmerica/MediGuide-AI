"""Health isolation for the AI-dependent capabilities added alongside the
transient-outage hardening work: Ollama being unreachable must degrade only
the capabilities that actually depend on it, never document storage/
preview or the app as a whole. Mirrors the existing isolation tests in
tests/test_imaging_api.py (test_ollama_outage_does_not_affect_imaging_document_health)
for the two new probes this feature adds.
"""

from __future__ import annotations


def test_ollama_outage_marks_ai_extraction_limited_not_unavailable(api_client, monkeypatch):
    import api as api_module

    monkeypatch.setattr(api_module, "_probe_ollama", lambda: (False, "simulated Ollama outage", set()))
    response = api_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()

    assert body["statuses"]["ollama"]["status"] == "unavailable"
    # "degraded" (rendered as "Limited" in the UI — see friendlyComponentStatus
    # in polish-ui.tsx), never "unavailable": the underlying storage/DB is
    # fine, only AI-assisted extraction is affected.
    assert body["statuses"]["imaging_reports"]["status"] == "degraded"
    assert body["statuses"]["medication_labels"]["status"] == "degraded"


def test_ollama_outage_leaves_storage_and_preview_ready(api_client, monkeypatch):
    import api as api_module

    monkeypatch.setattr(api_module, "_probe_ollama", lambda: (False, "simulated Ollama outage", set()))
    response = api_client.get("/api/health")
    body = response.json()

    assert body["statuses"]["database"]["status"] == "ready"
    assert body["statuses"]["document_processing"]["status"] == "ready"
    assert body["statuses"]["imaging_documents"]["status"] == "ready"
    assert body["status"] == "ok"


def test_imaging_storage_outage_marks_imaging_reports_unavailable_not_degraded(api_client, monkeypatch):
    """A real storage-layer failure (not just Ollama) is a harder failure
    than "limited" — imaging_reports must say so, not soften it to
    "degraded" just because that's the same bucket Ollama outages use."""
    import api as api_module

    monkeypatch.setattr(
        api_module, "probe_imaging_documents", lambda: (False, "simulated imaging DB outage")
    )
    response = api_client.get("/api/health")
    body = response.json()
    assert body["statuses"]["imaging_reports"]["status"] == "unavailable"


def test_system_status_lists_the_new_capabilities(api_client):
    response = api_client.get("/api/system/status")
    assert response.status_code == 200
    keys = {component["key"] for component in response.json()["components"]}
    assert "imaging_reports" in keys
    assert "medication_labels" in keys


def test_health_reports_ai_unavailable_when_ollama_is_down(api_client, monkeypatch):
    """The frontend hides chat and explanation actions on this flag, so it
    must be false whenever the text model can't be reached."""
    import api as api_module

    monkeypatch.setattr(api_module, "_probe_ollama", lambda: (False, "simulated outage", set()))
    body = api_client.get("/api/health").json()
    assert body["ai_available"] is False
