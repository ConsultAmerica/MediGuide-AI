"""Strict parsing of one lab-report text line into a measurement.

Why this exists: the previous native-text parser accepted any line shaped
like "<words> <number><anything>", so report metadata was mapped into
measurement fields — "Specimen collected: 01/15/2026" became value "01" with
unit "/15/2026", "Reference range: 4.0-11.0" became value "4.0" with unit
"-11", and "Glucose 101 H mg/dL Ref 70-99" became a test named
"Glucose 101 H mg/dL Ref" with value "70".

The rules here prefer *not* producing a field over producing a wrong one:

* metadata lines (dates, demographics, contact details, identifiers, page
  furniture, standalone reference ranges) never become measurements;
* a line must match the full grammar ``label value [flag] [unit] [flag]
  [reference range]``; leftover text that looks like data rejects the line;
* anything parsed but not fully certain is returned with
  ``needs_review=True`` so the person reviewing sees it flagged.

Values, units and ranges are returned exactly as printed; nothing is
rounded, converted or corrected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Label prefixes that describe the report, the patient or the page rather
# than a measured analyte. Matched case-insensitively at the start of the
# label, on word boundaries ("Tel:" is metadata, "Telopeptide" is not).
# "Fasting" and "Sex" only count when they aren't the start of a test name:
# "Fasting: Yes" is metadata, "Fasting Glucose" and "Sex Hormone Binding
# Globulin" are results.
_METADATA_LABEL = re.compile(
    r"^(?:"
    r"specimen|sample|collect(?:ed|ion)?|received|reported?|printed|resulted|"
    r"verified\s+by|ordered|date|time|dob|birth|age|sex(?!\s+hormone)|gender|"
    r"patient|name|mrn|id\b|accession|account|order|requisition|visit|"
    r"page|phone|tel|fax|address|zip|city|state|"
    r"provider|physician|doctor|dr\b|clinician|ordering|lab(?:oratory)?\s+(?:name|director|id)|"
    r"fasting(?=\s*(?:[:?]|$|\d|(?:status|state|yes|no|hours?|hrs?)\b))|comments?|notes?|interpretation|method|"
    r"ref(?:erence)?\b|range\b|normal\s+range|limits?\b|units?\b|result\b|test\b|component\b"
    r")\b",
    re.I,
)

# A date or time anywhere in the line. Measurement rows don't carry these;
# metadata rows do. Separators must repeat and years are four digits unless
# slashes make the date unambiguous, so a range like "4.0-11.0" never counts.
_DATE_OR_TIME = re.compile(
    r"\b\d{4}([-/.])\d{1,2}\1\d{1,2}\b"
    r"|\b\d{1,2}([-/.])\d{1,2}\2\d{4}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2}\b"
    r"|\b\d{1,2}:\d{2}\b"
)

_FLAG = r"(?:HH|LL|H|L|A|High|Low|Abnormal|Critical|\*)"

# A unit as printed on lab reports: %, g/dL, mg/dL, mmol/L, 10^3/uL,
# x10^9/L, 10*3/uL, fL, pg, U/L, mIU/L, µg/dL ... A unit never starts with
# "-" or "/" followed by digits (that is a date or range fragment).
_UNIT = (
    r"(?:%"
    r"|x?\s?10\s?[\^*]\s?\d+\s?/\s?[A-Za-zµμ]+"
    r"|[A-Za-zµμ][A-Za-z0-9µμ^*/.]*)"
)

# A unit printed *after* the reference range ("70 - 99 mg/dL"). Stricter than
# _UNIT so a trailing word such as "borderline" is never taken for a unit.
_UNIT_AFTER_RANGE = (
    r"(?:%"
    r"|x?\s?10\s?[\^*]\s?\d+\s?/\s?[A-Za-zµμ]+"
    r"|[A-Za-zµμ]*\s?/\s?[A-Za-zµμ0-9.]+"
    r"|fL|pg|sec|IU|U|mEq|mmHg)"
)

_NUMBER = r"\d+(?:\.\d+)?"
_RANGE = (
    rf"(?:[<>]=?\s?{_NUMBER}"
    rf"|{_NUMBER}\s*(?:-|–|—|to)\s*{_NUMBER})"
)

_LINE = re.compile(
    r"^(?P<label>[A-Za-z][A-Za-z0-9 ,/_\-().'+]*?[A-Za-z0-9)])"
    r"\s*[:=]?\s+"
    # (?![\d.]): a value never ends mid-number ("70 - 99" must not become
    # value "7" with range "0 - 99").
    rf"(?P<value>(?:[<>]=?\s?)?{_NUMBER})(?![\d.])"
    rf"(?:\s+(?P<flag1>{_FLAG})(?=\s|$))?"
    rf"(?:\s+(?P<unit>{_UNIT}))?"
    rf"(?:\s+(?P<flag2>{_FLAG})(?=\s|$))?"
    r"(?:\s+(?:Ref(?:erence)?(?:\s*range)?|Range|Normal(?:\s*range)?|Limits)\s*[:=]?)?"
    rf"(?:\s*[\[(]?\s*(?P<ref>{_RANGE})(?:\s*[\])])?)?"
    rf"(?:\s+(?P<unit2>{_UNIT_AFTER_RANGE})(?=\s|$))?"
    # Digit-free trail: when a label itself has digits ("Vitamin D 25-OH")
    # the engine backtracks to the longer label instead of leaving data
    # unexplained.
    r"(?P<trail>[^\d]*)$",
    re.I,
)

# A label that contains a value-with-unit or a range swallowed data from the
# row ("Glucose 96 mg/dL 70-99"); never accept it.
_EMBEDDED_RESULT = re.compile(
    rf"{_NUMBER}\s*(?:%|[A-Za-zµμ]+\s?/\s?[A-Za-zµμ]|x?10\s?[\^*])|\d\s*(?:-|–|—|to)\s*\d",
    re.I,
)

# Words that mark page furniture or report metadata wherever they appear in
# a label, and connector words a real analyte name never ends with.
_NON_ANALYTE_WORD = re.compile(r"\b(?:page|report|visit|specimen|patient|printed|received|collected)\b", re.I)
_DANGLING_END = re.compile(r"\b(?:of|to|and|per|from|by|at)$", re.I)

# A printed unit somewhere in a line: worth a human look when the line
# can't be parsed confidently.
_UNIT_HINT = re.compile(r"%|[A-Za-zµμ]+\s?/\s?[A-Za-zµμ]+|x?10\s?[\^*]\s?\d", re.I)

_FLAG_WORDS = {"h": "H", "hh": "HH", "high": "H", "l": "L", "ll": "LL", "low": "L"}

# Label for a line that looks like a result but could not be parsed safely.
# Deliberately generic so it can never normalize to a tracked lab test.
UNREAD_LINE_LABEL = "Unread line"


@dataclass(frozen=True)
class ParsedMeasurement:
    label: str
    value: str
    unit: str
    reference_range: str
    flag: str          # "H", "L", "HH", "LL", "A", "*" or "" as printed
    needs_review: bool
    source_text: str


def is_metadata_label(label: str) -> bool:
    return bool(_METADATA_LABEL.match(label.strip()))


def _letters(text: str) -> int:
    return sum(ch.isalpha() for ch in text)


def parse_lab_line(line: str) -> ParsedMeasurement | None:
    """Return the measurement printed on ``line``, or None when the line is
    not a measurement (or cannot be parsed without guessing)."""
    text = " ".join(line.split())
    if not text or _DATE_OR_TIME.search(text):
        return None

    match = _LINE.match(text)
    if not match:
        return None

    label = match.group("label").strip(" :=-")
    value = match.group("value").replace(" ", "")
    unit = (match.group("unit") or "").strip()
    unit_after_range = (match.group("unit2") or "").strip()
    reference_range = (match.group("ref") or "").strip()
    flag = (match.group("flag1") or match.group("flag2") or "").strip()
    trail = (match.group("trail") or "").strip()

    if (
        _letters(label) < 2
        or is_metadata_label(label)
        or _NON_ANALYTE_WORD.search(label)
        or _DANGLING_END.search(label)
        or _EMBEDDED_RESULT.search(label)
        # A free-standing number in the name ("Gluc0se 1l2 70") means a
        # value or range column was swallowed; analyte names don't have one.
        or re.search(rf"(?:^|\s)(?:[<>]=?)?{_NUMBER}(?=\s|$)", label)
    ):
        return None
    # A flag word swallowed as the unit ("Glucose 101 H Ref 70-99").
    if unit.lower() in _FLAG_WORDS and not flag:
        flag, unit = unit, ""
    needs_review = bool(trail)
    # Column order "value [flag] range unit" ("112 H 70 - 99 mg/dL").
    if unit_after_range:
        if unit:
            needs_review = True  # two units printed: don't pick one
        else:
            unit = unit_after_range
    return ParsedMeasurement(
        label=label,
        value=value,
        unit=unit,
        reference_range=reference_range,
        flag=_FLAG_WORDS.get(flag.lower(), flag.upper() if flag else ""),
        needs_review=needs_review,
        source_text=text,
    )


# --------------------------------------------------------------------- dates

_DATE_VALUE = r"(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4})"
_COLLECTION_DATE = re.compile(
    r"(?:Collection\s*date|Date\s*collected|Specimen\s*collected|Collected|Date\s*of\s*service)"
    rf"\s*[:\s]\s*{_DATE_VALUE}",
    re.I,
)
_REPORT_DATE = re.compile(
    rf"(?:Report\s*date|Date\s*reported|Reported)\s*[:\s]\s*{_DATE_VALUE}",
    re.I,
)


@dataclass(frozen=True)
class ParsedDate:
    label: str          # "Collection date" or "Report date", as printed
    value: str
    source_text: str


def find_result_dates(text: str) -> list[ParsedDate]:
    """Every result date printed on the page, collection before report.
    Both are kept (and labelled as printed) because they are different
    clinical facts; the timeline prefers the collection date."""
    dates: list[ParsedDate] = []
    for pattern, label in ((_COLLECTION_DATE, "Collection date"), (_REPORT_DATE, "Report date")):
        found = pattern.search(text)
        if found:
            dates.append(ParsedDate(label=label, value=found.group(1), source_text=found.group(0).strip()))
    return dates


def find_result_date(text: str) -> ParsedDate | None:
    """The date the results belong to. Collection date is preferred because
    it is when the measurement was taken; the report date is used only when
    no collection date is printed. The label always says which one it is."""
    for pattern, label in ((_COLLECTION_DATE, "Collection date"), (_REPORT_DATE, "Report date")):
        found = pattern.search(text)
        if found:
            return ParsedDate(label=label, value=found.group(1), source_text=found.group(0).strip())
    return None


def looks_like_date(value: str) -> bool:
    """A calendar date as printed (a bare time of day doesn't count)."""
    text = value.strip()
    if re.fullmatch(r"\d{1,2}:\d{2}", text):
        return False
    return bool(_DATE_OR_TIME.fullmatch(text))


def is_unparsed_result_line(line: str) -> bool:
    """True when a line looks like a printed result (name, number, unit) but
    did not parse cleanly. Such lines are surfaced for manual review rather
    than dropped silently."""
    text = " ".join(line.split())
    if not text or _DATE_OR_TIME.search(text) or is_metadata_label(text) or _NON_ANALYTE_WORD.search(text):
        return False
    looks_like_result = _letters(text) >= 2 and re.search(r"\d", text) and _UNIT_HINT.search(text)
    return bool(looks_like_result) and parse_lab_line(text) is None


# ------------------------------------------------------- model output check

def check_extracted_measurement(label: str, value: str, unit: str) -> str:
    """Classify a measurement proposed by the vision model.

    Returns "ok", "review" (keep, but flag for manual review) or "reject"
    (not a measurement: metadata, a date, or a reference-range fragment).
    """
    label = label.strip()
    value = value.strip()
    unit = unit.strip()
    if not label or _letters(label) < 2:
        return "reject"
    if is_metadata_label(label):
        return "reject"
    if _DATE_OR_TIME.search(value) or re.match(r"^[-/]\d", unit):
        return "reject"
    if not re.match(rf"^(?:[<>]=?\s?)?{_NUMBER}$", value):
        # Qualitative results ("Negative", "Positive") are legitimate but
        # can't be range-checked mechanically: keep them for a human.
        return "review"
    return "ok"
