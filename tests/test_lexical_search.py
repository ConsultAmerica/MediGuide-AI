"""Keyword search and the sources-only chat mode used where no model runs."""

from src import lexical_search, rag_chatbot, retriever


def test_keyword_search_finds_the_matching_approved_source():
    titles = [chunk.metadata["title"] for chunk in lexical_search.search("What is diabetes in plain language?")]
    assert titles and "Diabetes" in titles[0]


def test_keyword_search_returns_nothing_for_unrelated_questions():
    assert lexical_search.search("quantum chromodynamics football") == []


def test_best_passage_quotes_the_text_verbatim():
    text = "Cats are small. Diabetes affects blood sugar. It is common. Dogs bark loudly."
    passage = lexical_search.best_passage(text, "diabetes blood sugar")
    assert "Diabetes affects blood sugar." in passage
    assert passage in text


def _run_without_models(monkeypatch, question):
    monkeypatch.setattr(retriever, "vector_search_available", lambda: False)
    monkeypatch.setattr(rag_chatbot, "text_model_ready", lambda: False)
    return list(rag_chatbot.stream_rag_events(question))


def test_chat_quotes_approved_sources_when_no_model_is_available(monkeypatch):
    done = _run_without_models(monkeypatch, "What is high blood pressure?")[-1]
    assert done["type"] == "done"
    assert done["status"] == "sources_only"
    assert done["sources"]
    assert "AI writing is switched off" in done["answer"]
    assert "[1]" in done["answer"]


def test_chat_without_a_model_still_reports_missing_evidence(monkeypatch):
    done = _run_without_models(monkeypatch, "quantum chromodynamics football")[-1]
    assert done["status"] == "no_evidence"


def test_health_reports_sources_mode_without_a_model(api_client, monkeypatch):
    import api as api_module

    monkeypatch.setattr(api_module, "_probe_ollama", lambda: (False, "simulated outage", set()))
    body = api_client.get("/api/health").json()
    assert body["ai_available"] is False
    assert body["answer_mode"] == "sources"
