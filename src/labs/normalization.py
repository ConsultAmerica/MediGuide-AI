"""Lab test names, units, values and reference ranges.

Everything here is deliberately conservative:

* Test names are matched against a reviewed alias list. Tests that are
  clinically different (fasting vs random glucose, hemoglobin vs HbA1c,
  creatinine vs eGFR) are kept apart, and a name that isn't on the list
  keeps its own identity instead of being guessed into a known test.
* Units are only treated as the same when they are different spellings of
  the same unit (mg/dl and mg/dL; K/uL and 10^3/uL). Nothing is converted
  between units.
* A value is only numeric when it is a plain number. "<0.5", ">90",
  "Positive" or "1.0-2.0" are kept as printed and never plotted as numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Reviewed alias catalog: code -> (display name, aliases). Aliases are compared
# after _name_key() normalization (lowercase, punctuation to spaces).
LAB_CATALOG: dict[str, tuple[str, tuple[str, ...]]] = {
    "hemoglobin": ("Hemoglobin", ("hemoglobin", "haemoglobin", "hgb", "hb", "hemoglobin blood")),
    "hemoglobin_a1c": ("Hemoglobin A1C", (
        "hemoglobin a1c", "haemoglobin a1c", "hba1c", "hb a1c", "a1c", "glycated hemoglobin",
        "glycohemoglobin", "glycosylated hemoglobin", "hemoglobin a1c hba1c",
    )),
    "glucose": ("Glucose", ("glucose", "blood glucose", "glucose serum", "glucose plasma", "serum glucose", "random glucose")),
    # Fasting glucose has its own reference range; it is not merged with glucose.
    "glucose_fasting": ("Glucose, Fasting", ("fasting glucose", "glucose fasting", "fasting blood glucose", "fbg", "fbs", "fasting blood sugar")),
    "ldl_cholesterol": ("LDL Cholesterol", ("ldl", "ldl cholesterol", "ldl c", "ldl calculated", "ldl cholesterol calculated", "ldl chol calc", "ldl chol")),
    "hdl_cholesterol": ("HDL Cholesterol", ("hdl", "hdl cholesterol", "hdl c", "hdl chol")),
    "total_cholesterol": ("Cholesterol", ("cholesterol", "total cholesterol", "cholesterol total", "chol")),
    "triglycerides": ("Triglycerides", ("triglycerides", "triglyceride", "trig", "trigs", "tg")),
    "creatinine": ("Creatinine", ("creatinine", "serum creatinine", "creatinine serum", "creat")),
    "egfr": ("eGFR", ("egfr", "estimated gfr", "gfr estimated", "egfr non afr american", "egfr creatinine")),
    "bun": ("Urea Nitrogen (BUN)", ("bun", "urea nitrogen", "blood urea nitrogen", "urea nitrogen bun")),
    "sodium": ("Sodium", ("sodium", "na", "sodium serum")),
    "potassium": ("Potassium", ("potassium", "k", "potassium serum")),
    "chloride": ("Chloride", ("chloride", "cl")),
    "bicarbonate": ("Carbon Dioxide (CO2)", ("carbon dioxide", "co2", "bicarbonate", "hco3", "total co2", "carbon dioxide total")),
    "calcium": ("Calcium", ("calcium", "ca", "calcium serum")),
    "albumin": ("Albumin", ("albumin", "albumin serum")),
    "total_protein": ("Total Protein", ("total protein", "protein total")),
    "alkaline_phosphatase": ("Alkaline Phosphatase", ("alkaline phosphatase", "alk phos", "alp")),
    "bilirubin_total": ("Bilirubin, Total", ("bilirubin total", "total bilirubin", "bilirubin", "t bili", "tbil")),
    "alt": ("ALT", ("alt", "alanine aminotransferase", "sgpt", "alt sgpt")),
    "ast": ("AST", ("ast", "aspartate aminotransferase", "sgot", "ast sgot")),
    "wbc": ("WBC", ("wbc", "white blood cell", "white blood cells", "white blood cell count", "wbc count", "leukocytes")),
    "rbc": ("RBC", ("rbc", "red blood cell", "red blood cells", "red blood cell count", "rbc count", "erythrocytes")),
    "hematocrit": ("Hematocrit", ("hematocrit", "haematocrit", "hct")),
    "mcv": ("MCV", ("mcv", "mean corpuscular volume")),
    "platelets": ("Platelets", ("platelets", "platelet", "platelet count", "plt")),
    "tsh": ("TSH", ("tsh", "thyroid stimulating hormone", "thyrotropin")),
    "free_t4": ("Free T4", ("free t4", "t4 free", "ft4", "free thyroxine")),
    "vitamin_d_25oh": ("Vitamin D, 25-Hydroxy", ("vitamin d 25 hydroxy", "25 hydroxy vitamin d", "25 oh vitamin d", "vitamin d 25 oh", "vitamin d")),
    "ferritin": ("Ferritin", ("ferritin",)),
    "uric_acid": ("Uric Acid", ("uric acid",)),
}

# The tests Labs offers before any results exist (and the original tracked set).
TRACKED_LAB_CODES = {
    code: LAB_CATALOG[code][0]
    for code in (
        "hemoglobin", "hemoglobin_a1c", "glucose", "ldl_cholesterol", "hdl_cholesterol",
        "total_cholesterol", "triglycerides", "creatinine", "wbc", "platelets", "alt", "ast",
    )
}


def _name_key(name: str) -> str:
    text = (name or "").lower().replace("µ", "u")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


TEST_NAME_MAP: dict[str, str] = {
    _name_key(alias): code for code, (_, aliases) in LAB_CATALOG.items() for alias in aliases
}
TEST_NAME_MAP.update({code.replace("_", " "): code for code in LAB_CATALOG})


def _lookup(key: str) -> Optional[str]:
    return TEST_NAME_MAP.get(key)


def normalize_test_name(name: str) -> str:
    """Catalog code for a printed test name, or a stable code of its own.

    "Glucose, Fasting" and "Fasting Glucose" both map to glucose_fasting; a
    trailing parenthetical is tried on its own ("Hemoglobin A1c (HbA1c)").
    An unknown name is never guessed into a catalog test: it gets a code
    derived from its own words.
    """
    raw = (name or "").strip()
    key = _name_key(raw)
    if not key:
        return ""
    found = _lookup(key)
    if found:
        return found
    paren = re.match(r"^(.*?)\(([^)]*)\)\s*$", raw)
    if paren:
        for part in (paren.group(1), paren.group(2)):
            found = _lookup(_name_key(part))
            if found:
                return found
    return key.replace(" ", "_")[:64]


def display_name_for(code: str, printed_name: str) -> str:
    entry = LAB_CATALOG.get(code)
    return entry[0] if entry else (printed_name or code).strip()


def is_tracked_lab(code_or_name: str) -> bool:
    return normalize_test_name(code_or_name) in TRACKED_LAB_CODES


def is_catalog_lab(code_or_name: str) -> bool:
    return normalize_test_name(code_or_name) in LAB_CATALOG


# --------------------------------------------------------------------- values

_PLAIN_NUMBER = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
_QUALIFIER = re.compile(r"^(<=|>=|≤|≥|<|>)\s*([+-]?\d+(?:\.\d+)?)$")
# What may follow a number in the value cell without changing its meaning:
# a unit-like word or a printed flag. Anything else makes the value textual.
_TRAILING_OK = re.compile(r"^(?:[A-Za-zµ%/^*0-9.]+(?:/[A-Za-z0-9.^*]+)*|H|L|HH|LL|A|\*)$")


@dataclass(frozen=True)
class ParsedValue:
    numeric: Optional[float]   # plottable number, only for a plain value
    qualifier: str             # "<", ">", "<=", ">=" when printed as a bound
    bound: Optional[float]     # the number after a qualifier


def parse_value(text: str) -> ParsedValue:
    cleaned = (text or "").strip().replace("≤", "<=").replace("≥", ">=")
    if not cleaned:
        return ParsedValue(None, "", None)
    qualified = _QUALIFIER.match(cleaned)
    if qualified:
        return ParsedValue(None, qualified.group(1), float(qualified.group(2)))
    head, _, rest = cleaned.partition(" ")
    head = head.rstrip("%") if not rest else head
    if _PLAIN_NUMBER.match(head) and (not rest or _TRAILING_OK.match(rest.strip())):
        return ParsedValue(float(head.replace(",", "")), "", None)
    return ParsedValue(None, "", None)


def parse_numeric_value(value: str) -> Optional[float]:
    """The plottable number in a value, or None when it isn't a plain number."""
    return parse_value(value).numeric


# ---------------------------------------------------------------------- units

# Spelling variants only. Two spellings share a key only when they are the
# same unit by definition (1 K/uL == 1 x10^3/uL == 1 x10^9/L; 1 U/L == 1 IU/L;
# 1 uIU/mL == 1 mIU/L). No numeric conversion happens anywhere.
_UNIT_KEYS: dict[str, str] = {
    "mg/dl": "mg/dL",
    "g/dl": "g/dL",
    "g/l": "g/L",
    "mmol/l": "mmol/L",
    "umol/l": "umol/L",
    "meq/l": "mEq/L",
    "%": "%",
    "ng/ml": "ng/mL",
    "pg/ml": "pg/mL",
    "ng/dl": "ng/dL",
    "ug/dl": "ug/dL",
    "fl": "fL",
    "pg": "pg",
    "mm/hr": "mm/h",
    "mm/h": "mm/h",
    "u/l": "U/L",
    "iu/l": "U/L",
    "uiu/ml": "mIU/L",
    "miu/l": "mIU/L",
    "ml/min/1.73m2": "mL/min/1.73m2",
    "ml/min/1.73 m2": "mL/min/1.73m2",
    "10^3/ul": "10^3/uL",
    "10*3/ul": "10^3/uL",
    "x10^3/ul": "10^3/uL",
    "x10e3/ul": "10^3/uL",
    "10e3/ul": "10^3/uL",
    "k/ul": "10^3/uL",
    "thou/ul": "10^3/uL",
    "10^9/l": "10^3/uL",
    "x10^9/l": "10^3/uL",
    "10^6/ul": "10^6/uL",
    "10*6/ul": "10^6/uL",
    "x10^6/ul": "10^6/uL",
    "x10e6/ul": "10^6/uL",
    "m/ul": "10^6/uL",
    "mill/ul": "10^6/uL",
    "10^12/l": "10^6/uL",
}


def _unit_lookup(unit: str) -> str:
    text = (unit or "").strip().replace("µ", "u").replace("μ", "u")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def unit_key(unit: str) -> str:
    """Comparison key: two units with the same key are the same unit."""
    lookup = _unit_lookup(unit)
    if not lookup:
        return ""
    return _UNIT_KEYS.get(lookup, _UNIT_KEYS.get(lookup.replace(" ", ""), lookup))


UNIT_MAP = {alias: canonical for alias, canonical in _UNIT_KEYS.items()}


def normalize_unit(unit: str) -> str:
    """Tidy the spelling of a known unit (mg/dl -> mg/dL); unknown units are
    kept exactly as printed. Notation variants (K/uL) are kept as printed;
    unit_key() is what decides whether two units are the same."""
    cleaned = (unit or "").strip()
    if not cleaned:
        return ""
    lookup = _unit_lookup(cleaned)
    canonical = _UNIT_KEYS.get(lookup)
    # Only case/spacing fixes are applied to the stored unit, never a swap
    # to a different notation, so the original unit stays visible.
    if canonical and canonical.lower() == lookup:
        return canonical
    return cleaned


# ----------------------------------------------------------- reference ranges

def parse_reference_range(text: str) -> tuple[Optional[float], Optional[float]]:
    """Numeric bounds of a printed range when they are unambiguous."""
    if not text:
        return None, None
    cleaned = (
        text.replace(",", "")
        .replace("–", "-")
        .replace("—", "-")
        .replace("≤", "<=")
        .replace("≥", ">=")
        .strip()
    )
    between = re.fullmatch(
        r"[\[(]?\s*(-?\d+(?:\.\d+)?)\s*(?:-|to)\s*(-?\d+(?:\.\d+)?)\s*[\])]?\s*[A-Za-z%/^0-9.]*",
        cleaned,
        flags=re.IGNORECASE,
    )
    if between:
        low, high = float(between.group(1)), float(between.group(2))
        return (low, high) if low <= high else (None, None)
    comparison = re.fullmatch(r"(<=|>=|<|>|up to|under|below|over|above)\s*(-?\d+(?:\.\d+)?)\s*[A-Za-z%/^0-9.]*", cleaned, flags=re.IGNORECASE)
    if comparison:
        operator, bound_text = comparison.groups()
        bound = float(bound_text)
        if operator.lower() in {"<", "<=", "up to", "under", "below"}:
            return None, bound
        return bound, None
    return None, None
