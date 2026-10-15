"""Stage F3.6: medication labels, prescriptions and medication lists.

Synthetic label text only. Covers brand vs generic names, strength vs dose,
frequency, unclear and missing directions, several medications in one
document, per-medication review, corrections kept, and duplicates and
conflicting records shown for review (never merged, never auto-chosen).
"""

from __future__ import annotations

import pymupdf
import pytest

from src.medications.label_parser import lines_from_text, name_key, parse_label


def _parse(text):
    return [{key: value.value for key, value in entry.fields.items()} | {"_notes": entry.review_notes,
            "_flags": {key: value.flags for key, value in entry.fields.items()}} for entry in parse_label(lines_from_text(text))]


# -------------------------------------------------------------------- parser

def test_brand_and_generic_only_when_the_label_says_which_is_which():
    (entry,) = _parse("Metformin HCl 500 mg tablet\nGeneric for: Glucophage\nTake 1 tablet by mouth twice daily")
    assert entry["generic_name"] == "Metformin HCl" and entry["brand_name"] == "Glucophage"

    (unlabelled,) = _parse("Glucophage (metformin) 500 mg tablet\nTake 1 tablet by mouth daily")
    assert "brand_name" not in unlabelled and "generic_name" not in unlabelled
    assert "second_name_in_brackets" in unlabelled["_flags"]["medication_name"]


def test_strength_is_never_turned_into_a_dose_or_daily_amount():
    (entry,) = _parse("Metformin 500 mg tablets\nTake 2 tablets by mouth twice daily with meals")
    assert entry["strength"] == "500 mg"
    assert entry["dose"] == "2 tablets"
    assert entry["frequency"] == "twice daily, with meals"
    assert entry["route"] == "by mouth"
    assert not any("1000" in str(v) or "2000" in str(v) for v in entry.values())

    (no_directions,) = _parse("Metformin 500 mg tablets")
    assert "dose" not in no_directions and "frequency" not in no_directions
    assert "missing_directions" in no_directions["_notes"]


@pytest.mark.parametrize("directions,frequency", [
    ("Take 1 tablet by mouth once daily", "once daily"),
    ("Take 1 capsule three times a day", "three times a day"),
    ("Take 1 tablet every 8 hours", "every 8 hours"),
    ("Take 1 tablet at bedtime", "at bedtime"),
    ("Take 1 tablet every other day", "every other day"),
    ("Take 1 tablet by mouth as needed for pain", "as needed for pain"),
    ("Take 1 tablet BID", "BID"),
])
def test_frequency_is_read_from_the_directions_as_printed(directions, frequency):
    (entry,) = _parse(f"Example 10 mg tablet\n{directions}")
    assert entry["frequency"] == frequency
    assert "from_directions" in entry["_flags"]["frequency"]
    assert entry["directions"] == directions


@pytest.mark.parametrize("directions,note", [
    ("Take as directed", "ambiguous_directions"),
    ("Use as instructed by your doctor", "ambiguous_directions"),
    ("Take 1 tablet QD", "risky_abbreviation"),
    ("Take 1 tablet QOD", "risky_abbreviation"),
    ("Take 1-2 tablets every 6 hours", "dose_range"),
    ("Take 1 tablet by mouth", "frequency_not_stated"),
])
def test_unclear_directions_are_flagged(directions, note):
    (entry,) = _parse(f"Example 10 mg tablet\n{directions}")
    assert note in entry["_notes"]


def test_a_medication_list_gives_one_entry_per_medication():
    entries = _parse(
        "Medication list\n"
        "Lisinopril 10 mg tablet - Take one tablet by mouth once daily\n"
        "Atorvastatin 20 mg tablets\nTake 1 tablet at bedtime\n"
        "Albuterol HFA 90 mcg/actuation inhaler\nInhale 2 puffs every 4 hours as needed\n"
    )
    assert [e["medication_name"] for e in entries] == ["Lisinopril", "Atorvastatin", "Albuterol HFA"]
    assert [e["strength"] for e in entries] == ["10 mg", "20 mg", "90 mcg/actuation"]
    assert entries[1]["directions"] == "Take 1 tablet at bedtime"
    assert entries[2]["route"] == "Inhale"


def test_label_details_are_separate():
    (entry,) = _parse(
        "Sample Pharmacy\nDate filled: 03/02/2026\nAmoxicillin 500 mg capsules\n"
        "Take 1 capsule by mouth three times daily for 10 days\nQty: 30 Refills: 0\nDr. Example Prescriber"
    )
    assert entry["quantity"] == "30" and entry["refills"] == "0"
    assert entry["pharmacy"] == "Sample Pharmacy" and entry["prescriber"] == "Dr. Example Prescriber"
    assert entry["prescription_date"] == "03/02/2026"
    assert entry["dosage_form"] == "capsules"


def test_similar_names_are_not_the_same_medication():
    assert name_key("Lisinopril 10 mg tablet") == name_key("LISINOPRIL tablets") == "lisinopril"
    assert name_key("Lisinopril-HCTZ 20-12.5 mg") != name_key("Lisinopril")


# ------------------------------------------------------------ through the API

@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    import src.medication_workspace as workspace

    def _fail(*args, **kwargs):
        raise AssertionError("the AI fallback should not run for readable labels")

    monkeypatch.setattr(workspace, "_ollama_client", _fail)


def _typed(client, text):
    response = client.post("/api/medications/v2/text", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def _confirm(client, state, index=0, *, edits=None, acknowledged=None, expect=200):
    entry = state["entries"][index]
    fields = [dict(f, value=(edits or {}).get(f["key"], f["value"])) for f in entry["fields"]]
    response = client.post(
        f"/api/medications/v2/{state['medication_id']}/entries/{entry['entry_id']}/confirm",
        json={"fields": fields, "reviewed": True, "acknowledged_record_ids": acknowledged or []},
    )
    assert response.status_code == expect, response.text
    return response.json()


LIST = (
    "Lisinopril 10 mg tablet - Take one tablet by mouth once daily\n"
    "Atorvastatin 20 mg tablets\nTake 1 tablet at bedtime\n"
    "Albuterol HFA 90 mcg/actuation inhaler\nInhale 2 puffs every 4 hours as needed\n"
)


def test_each_medication_in_a_list_is_reviewed_separately_and_nothing_is_added_by_itself(api_client):
    state = _typed(api_client, LIST)
    assert len(state["entries"]) == 3 and state["text_source"] == "typed"
    assert api_client.get("/api/medications/v2/records").json()["records"] == []   # nothing auto-added

    state = _confirm(api_client, state, 0)
    reject = api_client.post(f"/api/medications/v2/{state['medication_id']}/entries/{state['entries'][1]['entry_id']}/reject")
    assert reject.status_code == 200
    decisions = [e["decision"] for e in reject.json()["entries"]]
    assert decisions == ["confirmed", "rejected", "unverified"]

    records = api_client.get("/api/medications/v2/records").json()["records"]
    assert [r["medication_name"] for r in records] == ["Lisinopril"]
    record = records[0]
    assert record["strength"] == "10 mg" and record["dose"] == "one tablet" and record["frequency"] == "once daily"
    assert record["directions"] == "Take one tablet by mouth once daily"

    restored = api_client.post(f"/api/medications/v2/{state['medication_id']}/entries/{state['entries'][1]['entry_id']}/restore")
    assert restored.json()["entries"][1]["decision"] == "unverified"


def test_a_correction_is_kept_beside_what_was_read(api_client):
    state = _typed(api_client, "Amoxicillin 500 mg capsules\nTake as directed\nQty: 30 Refills: 0")
    entry = state["entries"][0]
    assert "ambiguous_directions" in entry["review_notes"]
    assert {f["key"]: f["confidence"] for f in entry["fields"]}["directions"] == "needs_review"

    state = _confirm(api_client, state, edits={"directions": "Take 1 capsule by mouth three times daily"})
    directions = next(f for f in state["entries"][0]["fields"] if f["key"] == "directions")
    assert directions["user_edited"] and directions["extracted"] == "Take as directed"

    record = api_client.get(f"/api/medications/v2/{state['medication_id']}/record").json()
    assert record["directions"] == "Take 1 capsule by mouth three times daily"
    assert record["extracted"]["directions"] == "Take as directed"
    assert "ambiguous_directions" in record["review_flags"]
    assert record["text_source"] == "typed"


def test_conflicting_records_are_shown_for_review_and_never_merged(api_client):
    first = _confirm(api_client, _typed(api_client, "Lisinopril 10 mg tablet\nTake 1 tablet by mouth once daily"))
    first_record = first["entries"][0]["record_id"]

    second = _typed(api_client, "LISINOPRIL 20 mg tablets\nTake 1 tablet by mouth once daily")
    (match,) = second["entries"][0]["matches"]
    assert match["record_id"] == first_record and match["kind"] == "conflict"
    assert [d["field"] for d in match["differences"]] == ["strength"]
    assert match["differences"][0]["this_label"] == "20 mg" and match["differences"][0]["existing_record"] == "10 mg"

    blocked = _confirm(api_client, second, expect=409)
    assert blocked["error"]["code"] == "MATCH_REVIEW_REQUIRED"
    _confirm(api_client, second, acknowledged=[first_record])

    records = api_client.get("/api/medications/v2/records").json()["records"]
    assert len(records) == 2                                            # both kept
    assert all(len(r["matches"]) == 1 and r["matches"][0]["kind"] == "conflict" for r in records)
    assert not any("current" in r for r in records)                     # neither chosen as current
    newer = next(r for r in records if r["strength"] == "20 mg")
    assert newer["acknowledged_records"] == [first_record]


def test_identical_details_are_a_possible_duplicate_and_different_drugs_do_not_match(api_client):
    _confirm(api_client, _typed(api_client, "Atorvastatin 20 mg tablet\nTake 1 tablet at bedtime"))
    again = _typed(api_client, "Atorvastatin 20 mg tablets\nTake 1 tablet at bedtime")
    assert again["entries"][0]["matches"][0]["kind"] == "possible_duplicate"
    other = _typed(api_client, "Rosuvastatin 20 mg tablet\nTake 1 tablet at bedtime")
    assert other["entries"][0]["matches"] == []


def test_another_account_cannot_see_or_confirm(api_client, other_user_headers):
    state = _typed(api_client, LIST)
    entry_id = state["entries"][0]["entry_id"]
    url = f"/api/medications/v2/{state['medication_id']}/entries/{entry_id}"
    assert api_client.post(f"{url}/confirm", json={"fields": state["entries"][0]["fields"], "reviewed": True},
                           headers=other_user_headers).status_code == 404
    assert api_client.post(f"{url}/reject", headers=other_user_headers).status_code == 404
    _confirm(api_client, state, 0)
    assert api_client.get("/api/medications/v2/records", headers=other_user_headers).json()["records"] == []


def test_education_needs_a_confirmed_medication(api_client):
    state = _typed(api_client, LIST)
    response = api_client.post(f"/api/medications/v2/{state['medication_id']}/info", json={})
    assert response.status_code == 409


def test_a_pdf_label_is_read_from_its_text_and_a_photo_by_local_ocr(api_client):
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(["Sample Pharmacy", "Metformin 500 mg tablets", "Take 1 tablet by mouth twice daily",
                              "Qty: 60 Refills: 2"]):
        page.insert_text((72, 90 + i * 26), line, fontsize=15)
    pdf = doc.tobytes()
    png = page.get_pixmap(dpi=200).tobytes("png")
    doc.close()

    from_pdf = api_client.post("/api/medications/v2/upload", files={"file": ("label.pdf", pdf, "application/pdf")}).json()
    assert from_pdf["text_source"] == "text_layer"
    assert {f["key"]: f["value"] for f in from_pdf["entries"][0]["fields"]}["frequency"] == "twice daily"

    from src.ocr import ocr_available

    if not ocr_available():
        pytest.skip("Tesseract is not installed")
    # Photo uploads used to be rejected outright ("Unsupported image format").
    photo = api_client.post("/api/medications/v2/upload", files={"file": ("label.png", png, "image/png")})
    assert photo.status_code == 200, photo.text
    from_photo = photo.json()
    assert from_photo["text_source"] == "ocr"
    values = {f["key"]: f["value"] for f in from_photo["entries"][0]["fields"]}
    assert values["medication_name"] == "Metformin" and values["strength"] == "500 mg"


def test_dose_wording_and_form_plurals_are_compared_as_the_same_amount():
    from src.medications.label_parser import comparable

    assert comparable("dose", "one tablet") == comparable("dose", "1 tablet")
    assert comparable("dose", "2 tablets") != comparable("dose", "1 tablet")
    assert comparable("dosage_form", "tabs") == comparable("dosage_form", "Tablet")
    assert comparable("dosage_form", "capsules") != comparable("dosage_form", "tablets")


def test_confirmation_time_is_sent_with_its_time_zone(api_client):
    state = _confirm(api_client, _typed(api_client, "Atorvastatin 20 mg tablet\nTake 1 tablet at bedtime"))
    record = api_client.get(f"/api/medications/v2/{state['medication_id']}/record").json()
    assert record["confirmed_at"].endswith("+00:00")
