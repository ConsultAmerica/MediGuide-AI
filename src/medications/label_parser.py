"""Reads medication labels, prescriptions and medication lists from text.

Deterministic and conservative: every value is text that is printed on the
label (with the line it came from), and anything not printed stays empty.

* Strength ("500 mg") is what one unit contains. Dose ("1 tablet") is how
  much to take at a time, and only when the directions say so. One is never
  derived from the other, and no daily amount is ever calculated.
* Frequency, route and dose are read from the printed directions; they are
  marked as coming from the directions and the directions themselves are
  always kept exactly as printed.
* Brand and generic names are only filled when the label says which is
  which ("Generic for: ...", "Brand: ..."). A second name in brackets is
  kept as printed, not guessed into one or the other.
* Unclear directions ("as directed"), dose ranges, error-prone
  abbreviations (QD, QOD) and missing directions are flagged for review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

FIELD_LABELS: dict[str, str] = {
    "medication_name": "Medication name (as printed)",
    "brand_name": "Brand name",
    "generic_name": "Generic name",
    "strength": "Strength",
    "dosage_form": "Dosage form",
    "route": "Route",
    "dose": "Dose (amount per use)",
    "frequency": "How often",
    "directions": "Directions as printed",
    "quantity": "Quantity",
    "refills": "Refills",
    "prescriber": "Prescriber",
    "pharmacy": "Pharmacy",
    "prescription_date": "Prescription date",
}
FIELD_ORDER = list(FIELD_LABELS)
FROM_DIRECTIONS = {"dose", "frequency", "route"}

# Longest first, so "mcg/actuation" is never cut to "mcg".
_UNIT = r"(?:mcg/actuation|mcg/act|mcg/hr|mg/\s?5\s?mL|mg/\s?5\s?ml|mg/mL|mg/ml|mcg/mL|mEq|mcg|µg|ug|mg|mL|ml|units?|IU|g|%)"
_STRENGTH = re.compile(
    rf"(?<![\w.])(\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?\s*{_UNIT})(?![a-z])",
    re.IGNORECASE,
)
_FORMS = (
    r"extended[- ]release tablets?|delayed[- ]release capsules?|er tablets?|xr tablets?|"
    r"tablets?|tabs?|caplets?|capsules?|caps?|solution|suspension|syrup|elixir|cream|ointment|gel|lotion|"
    r"inhaler|aerosol|nebuli[sz]er solution|patch(?:es)?|injection|injectable|pen|drops?|spray|suppositor(?:y|ies)|"
    r"powder|granules|lozenges?|film"
)
_FORM = re.compile(rf"(?<![a-z])({_FORMS})(?![a-z])", re.IGNORECASE)
_DIRECTION_START = re.compile(
    r"^\s*(?:sig\s*[:.]?\s*)?(?:take|use|apply|inhale|instill|insert|place|chew|dissolve|inject|give|spray|"
    r"swallow|rub|unwrap|shake|mix|put)\b",
    re.IGNORECASE,
)
_DOSE = re.compile(
    r"\b(?:take|use|inhale|instill|insert|place|chew|dissolve|inject|give|spray|swallow|apply)\s+"
    r"((?:\d+(?:\.\d+)?(?:\s*(?:-|to|or)\s*\d+(?:\.\d+)?)?|one|two|three|four|half|one-half|1/2)\s+"
    r"(?:tablets?|capsules?|caps?|tabs?|puffs?|drops?|units?|sprays?|ml|mL|teaspoons?|tablespoons?|patch(?:es)?|"
    r"applicators?(?:ful)?|suppositor(?:y|ies)|lozenges?|pens?|vials?|packets?|scoops?|grams?|g|mg|mcg))",
    re.IGNORECASE,
)
_FREQUENCY = re.compile(
    r"\b(once\s+(?:a\s+)?daily|once\s+a\s+day|twice\s+(?:a\s+)?daily|twice\s+a\s+day|"
    r"(?:one|two|three|four|five|six|\d+)\s+times\s+(?:a\s+|per\s+|each\s+)?(?:day|daily|week|weekly)|"
    r"every\s+(?:\d+(?:\s*(?:-|to)\s*\d+)?|one|two|three|four|six|eight|twelve|other)\s+(?:hours?|days?|weeks?|morning|evening|night)|"
    r"every\s+(?:morning|evening|night|day|week|other\s+day)|"
    r"(?:daily|weekly|monthly|nightly)|at\s+bedtime|in\s+the\s+(?:morning|evening)|"
    r"before\s+(?:meals|breakfast|bedtime)|after\s+meals|with\s+meals|"
    r"as\s+needed(?:\s+for\s+[a-z ]+?)?(?=[.,;]|$)|"
    r"\b(?:qd|qod|bid|tid|qid|qhs|qam|qpm|q\d+h|prn)\b)",
    re.IGNORECASE,
)
_ROUTES: list[tuple[str, str]] = [
    (r"by\s+mouth|orally|\bpo\b", "by mouth"),
    (r"under\s+the\s+tongue|sublingual(?:ly)?", "under the tongue"),
    (r"subcutaneous(?:ly)?|under\s+the\s+skin|\bsubq\b|\bsc\b", "under the skin"),
    (r"intramuscular(?:ly)?|into\s+the\s+muscle|\bim\b", "into the muscle"),
    (r"(?:in|into)\s+(?:each|the|both|left|right)\s+eyes?|ophthalmic", "in the eye"),
    (r"(?:in|into)\s+(?:each|the|both|left|right)\s+ears?|otic", "in the ear"),
    (r"(?:in|into)\s+(?:each|the|both)\s+nostrils?|nasal(?:ly)?|intranasal", "in the nose"),
    (r"by\s+inhalation|\binhale\b", "by inhalation"),
    (r"rectal(?:ly)?", "rectally"),
    (r"vaginal(?:ly)?", "vaginally"),
    (r"(?:to|on)\s+(?:the\s+)?(?:skin|affected\s+area)|topical(?:ly)?", "on the skin"),
]
_AMBIGUOUS_DIRECTIONS = re.compile(
    r"\b(?:as\s+directed|as\s+instructed|as\s+before|as\s+prescribed|use\s+as\s+told|take\s+as\s+told|ut\s+dict)\b",
    re.IGNORECASE,
)
_INLINE_DIRECTION = re.compile(
    r"\b(?:sig\s*[:.]?\s*)?(?:take|use|apply|inhale|instill|insert|place|chew|dissolve|inject|give|spray|swallow)\b",
    re.IGNORECASE,
)
_RISKY_ABBREVIATIONS = re.compile(r"\b(?:qd|qod|q\.d\.|q\.o\.d\.|\d+\s*u\b|hs)\b", re.IGNORECASE)

_QUANTITY = re.compile(r"^\s*(?:qty|quantity|disp(?:ense)?|#)\s*[:.]?\s*(.+?)\s*$", re.IGNORECASE)
_REFILLS = re.compile(r"\b(?:refills?\s*(?:remaining|left|allowed)?\s*[:.]?\s*(\d+|none|no|zero)|(no)\s+refills)\b", re.IGNORECASE)
_PRESCRIBER = re.compile(
    r"^\s*(?:prescriber|prescribed\s+by|doctor|physician|provider|dr\.?)\s*[:.]?\s*(.+?)\s*$", re.IGNORECASE
)
_PRESCRIBER_DR = re.compile(r"^\s*([Dd][Rr]\.?\s+[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,3})\s*$")
_PHARMACY_LABELLED = re.compile(r"^\s*pharmacy\s*[:.]\s*(.+?)\s*$", re.IGNORECASE)
_PHARMACY_NAME = re.compile(r"^\s*([A-Z][\w&'.-]*(?:\s+[\w&'.-]+){0,5}\s+pharmacy)\b", re.IGNORECASE)
_DATE_LABELLED = re.compile(
    r"^\s*(?:date\s+(?:filled|written|prescribed|issued)|fill(?:ed)?\s+date|rx\s+date|date)\s*[:.]?\s*"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE,
)
_GENERIC_FOR = re.compile(r"\b(?:generic\s+(?:for|equivalent(?:\s+(?:to|for))?)|substituted\s+for|compare\s+to)\s*[:.]?\s*([A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*)?)", re.IGNORECASE)
_BRAND_LABELLED = re.compile(r"^\s*brand(?:\s+name)?\s*[:.]\s*(.+?)\s*$", re.IGNORECASE)
_GENERIC_LABELLED = re.compile(r"^\s*generic(?:\s+name)?\s*[:.]\s*(.+?)\s*$", re.IGNORECASE)
_RX_NUMBER = re.compile(r"^\s*(?:rx|prescription)\s*(?:#|no\.?|number)\s*[:.]?\s*[\w-]+\s*$", re.IGNORECASE)



@dataclass
class LabelLine:
    text: str
    page: int = 1
    confidence: float = 100.0   # OCR confidence of the least-sure word; 100 for typed/text layer


@dataclass
class FieldValue:
    value: str = ""
    source_text: str = ""
    page: int = 1
    flags: list[str] = field(default_factory=list)
    confidence: float = 100.0


@dataclass
class ParsedMedication:
    fields: dict[str, FieldValue]
    review_notes: list[str]          # flags for the whole entry, e.g. "missing_directions"
    first_line: int = 0


def _medication_line(text: str) -> Optional[re.Match]:
    """A line that names a medication: a word, then a strength. Directions
    ("Take 1 tablet ...") and labelled metadata are never medication lines."""
    if _DIRECTION_START.match(text) or _QUANTITY.match(text) or _PRESCRIBER.match(text) or _DATE_LABELLED.match(text):
        return None
    match = _STRENGTH.search(text)
    if not match:
        return None
    before = text[: match.start()].strip(" -–:,")
    return match if re.search(r"[A-Za-z]{3,}", before) else None


def _name_from_line(text: str, strength: re.Match) -> str:
    name = text[: strength.start()].strip(" -–:,")
    name = re.sub(r"^\s*(?:rx|medication|drug|med)\s*[:.]\s*", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip()


def _flags_for_directions(directions: str) -> list[str]:
    flags: list[str] = []
    if _AMBIGUOUS_DIRECTIONS.search(directions):
        flags.append("ambiguous_directions")
    if _RISKY_ABBREVIATIONS.search(directions):
        flags.append("risky_abbreviation")
    return flags


def parse_label(lines: list[LabelLine]) -> list[ParsedMedication]:
    """Every medication on the label or list, in order. Shared details
    (pharmacy, prescriber, date) printed once apply to each entry, and are
    marked as such."""
    clean = [line for line in lines if line.text.strip()]
    starts = [index for index, line in enumerate(clean) if _medication_line(line.text)]
    if not starts:
        return []

    shared: dict[str, FieldValue] = {}
    for line in clean:
        text = line.text.strip()
        if "pharmacy" not in shared:
            match = _PHARMACY_LABELLED.match(text) or _PHARMACY_NAME.match(text)
            if match:
                shared["pharmacy"] = FieldValue(match.group(1).strip(" -–"), text, line.page, [], line.confidence)
        if "prescriber" not in shared:
            match = _PRESCRIBER_DR.match(text) or _PRESCRIBER.match(text)
            if match and not _RX_NUMBER.match(text):
                shared["prescriber"] = FieldValue(match.group(1).strip(), text, line.page, [], line.confidence)
        if "prescription_date" not in shared:
            match = _DATE_LABELLED.match(text)
            if match:
                shared["prescription_date"] = FieldValue(match.group(1).strip(), text, line.page, [], line.confidence)

    entries: list[ParsedMedication] = []
    for position, start in enumerate(starts):
        stop = starts[position + 1] if position + 1 < len(starts) else len(clean)
        block = clean[start:stop]
        head = block[0]
        strength_match = _medication_line(head.text)
        assert strength_match is not None
        fields: dict[str, FieldValue] = {}
        fields["medication_name"] = FieldValue(_name_from_line(head.text, strength_match), head.text.strip(), head.page, [], head.confidence)
        strength_text = strength_match.group(1).strip()
        strength_flags = ["several_strengths"] if len(_STRENGTH.findall(head.text)) > 1 else []
        fields["strength"] = FieldValue(strength_text, head.text.strip(), head.page, strength_flags, head.confidence)
        form = _FORM.search(head.text[strength_match.end():]) or _FORM.search(head.text)
        if form:
            fields["dosage_form"] = FieldValue(form.group(1), head.text.strip(), head.page, [], head.confidence)
        bracket = re.search(r"\(([A-Za-z][\w\s-]{2,40})\)", head.text[: strength_match.start()])
        if bracket:
            fields["medication_name"].flags.append("second_name_in_brackets")

        direction_lines: list[LabelLine] = []
        rest = head.text[strength_match.end():]
        inline = _INLINE_DIRECTION.search(rest)
        if inline:
            direction_lines.append(LabelLine(rest[inline.start():].strip(" -–:,"), head.page, head.confidence))
        elif _FREQUENCY.search(rest):
            # e.g. "Levothyroxine 50 mcg tab QD": only a frequency is printed.
            after_form = rest[form.end():] if form and form.start() < len(rest) and rest[form.start():form.end()] == form.group(1) else rest
            direction_lines.append(LabelLine(after_form.strip(" -–:,"), head.page, head.confidence))
        for line in block[1:]:
            text = line.text.strip()
            if _DIRECTION_START.match(text) or (direction_lines and not _metadata(text) and not _medication_line(text) and text[:1].islower()):
                direction_lines.append(line)
                continue
            if not form and (form_match := _FORM.search(text)) and not _metadata(text):
                fields["dosage_form"] = FieldValue(form_match.group(1), text, line.page, [], line.confidence)
            if (match := _QUANTITY.match(text)):
                quantity = re.split(r"[.;,]?\s+refills?\b", match.group(1), flags=re.IGNORECASE)[0].strip(" .;,")
                fields["quantity"] = FieldValue(quantity, text, line.page, [], line.confidence)
            if (match := _REFILLS.search(text)):
                raw = (match.group(1) or match.group(2) or "").lower()
                fields["refills"] = FieldValue("0" if raw in {"no", "none", "zero"} else raw, text, line.page, [], line.confidence)
            if (match := _GENERIC_FOR.search(text)):
                fields["brand_name"] = FieldValue(match.group(1).strip(), text, line.page, [], line.confidence)
                fields["generic_name"] = FieldValue(fields["medication_name"].value, head.text.strip(), head.page, [], head.confidence)
            if (match := _BRAND_LABELLED.match(text)):
                fields["brand_name"] = FieldValue(match.group(1), text, line.page, [], line.confidence)
            if (match := _GENERIC_LABELLED.match(text)):
                fields["generic_name"] = FieldValue(match.group(1), text, line.page, [], line.confidence)
        for key, value in shared.items():
            if key not in fields:
                fields[key] = FieldValue(value.value, value.source_text, value.page,
                                         (["shared_detail"] if len(starts) > 1 else []), value.confidence)

        notes: list[str] = []
        if direction_lines:
            directions = " ".join(line.text.strip() for line in direction_lines)
            source = " / ".join(line.text.strip() for line in direction_lines)
            low = min(line.confidence for line in direction_lines)
            page = direction_lines[0].page
            dir_flags = _flags_for_directions(directions)
            fields["directions"] = FieldValue(directions, source, page, dir_flags, low)
            notes.extend(dir_flags)
            if (match := _DOSE.search(directions)):
                dose = match.group(1)   # as printed ("one tablet" stays "one tablet")
                dose_flags = ["from_directions"] + (["dose_range"] if re.search(r"\d\s*(?:-|to|or)\s*\d", dose) else [])
                fields["dose"] = FieldValue(dose, directions, page, dose_flags, low)
                if "dose_range" in dose_flags:
                    notes.append("dose_range")
            frequencies = _FREQUENCY.findall(directions)
            if frequencies:
                fields["frequency"] = FieldValue(", ".join(dict.fromkeys(f.strip() for f in frequencies)), directions, page, ["from_directions"], low)
            else:
                notes.append("frequency_not_stated")
            for pattern, _label in _ROUTES:
                route = re.search(pattern, directions, re.IGNORECASE)
                if route:
                    fields["route"] = FieldValue(route.group(0), directions, page, ["from_directions"], low)
                    break
        else:
            notes.append("missing_directions")
        if strength_flags:
            notes.append("several_strengths")
        entries.append(ParsedMedication(fields=fields, review_notes=list(dict.fromkeys(notes)), first_line=start))
    return entries


def _metadata(text: str) -> bool:
    return bool(_QUANTITY.match(text) or _REFILLS.search(text) or _PRESCRIBER.match(text) or _DATE_LABELLED.match(text)
                or _PHARMACY_LABELLED.match(text) or _PHARMACY_NAME.match(text) or _RX_NUMBER.match(text))


def lines_from_text(text: str) -> list[LabelLine]:
    return [LabelLine(line.strip()) for line in (text or "").splitlines() if line.strip()]


def name_key(name: str) -> str:
    """Comparison key for spotting the same medication across records: the
    printed name without strength, form or punctuation. Exact match only;
    similar-looking names are never treated as the same medication."""
    text = (name or "").lower()
    text = _STRENGTH.sub(" ", text)
    text = _FORM.sub(" ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9/.]+", "", (text or "").lower())


_NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "half": "1/2", "one-half": "1/2"}
_FORM_ALIASES = {"tab": "tablet", "tabs": "tablet", "caplet": "tablet", "caplets": "tablet", "cap": "capsule", "caps": "capsule"}


def comparable(key: str, value: str) -> str:
    """Comparison form of a detail: spacing, case and punctuation ignored;
    for the dosage form, plurals and common abbreviations too ("tabs" ==
    "tablet"). Different words are still different."""
    text = compact(value)
    if key == "dose":
        # "one tablet" and "1 tablet" are the same amount.
        words = (value or "").lower().split()
        words = [_NUMBER_WORDS.get(word, word) for word in words]
        text = compact(" ".join(word[:-1] if word.endswith("s") and not word.endswith("ss") else word for word in words))
    if key == "dosage_form":
        words = re.sub(r"[^a-z ]+", " ", (value or "").lower()).split()
        words = [_FORM_ALIASES.get(word, word) for word in words]
        words = [word[:-1] if word.endswith("s") and not word.endswith("ss") else word for word in words]
        text = " ".join(words)
    return text
