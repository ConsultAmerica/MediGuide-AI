"""Splits radiology report text into named sections, with their source.

Purely mechanical text splitting: this module never interprets, summarizes
or diagnoses. A section's text is exactly the report's own wording between
one recognized header and the next. If no recognized headers are found, the
caller gets an empty result rather than a guessed section, since a wrong
guess (e.g. calling the whole report "Findings") is worse than nothing.
Every extracted section is reviewed by the user before it is used anywhere.

The report is read as one sequence of lines across all pages, so a section
that continues onto the next page stays one section, and every section
knows which pages (and, when positions are available, which regions of
those pages) its wording came from.

It also reads, without guessing:

* which kind of report this looks like (``classify_report``): the imaging
  modality named in the report and whether the text reads like a radiology
  report at all;
* labelled details (``extract_report_details``): exam date, ordering
  clinician, performing facility and the exam description, only when the
  report prints them with a label.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

SECTION_TYPES = [
    "exam",
    "clinical_history",
    "technique",
    "comparison",
    "findings",
    "impression",
    "recommendations",
]

# Header wordings per section. A header only counts at the start of a line,
# followed by ":" (or a dash) or standing alone on its line, so prose such as
# "History of prior surgery." or "Examined structures..." inside the
# findings never starts a new section.
_SECTION_HEADER_PATTERNS: dict[str, list[str]] = {
    "exam": [
        r"exam(?:ination)?",
        r"exam(?:ination)?\s+type",
        r"type\s+of\s+exam(?:ination)?",
        r"study",
        r"procedure",
    ],
    "clinical_history": [
        r"clinical\s+history",
        r"clinical\s+info(?:rmation)?",
        r"clinical\s+indications?",
        r"indications?",
        r"reason\s+for\s+(?:exam(?:ination)?|study|referral)",
        r"history",
    ],
    "technique": [r"technique", r"protocol"],
    "comparison": [r"comparisons?", r"prior\s+stud(?:y|ies)"],
    "findings": [r"findings"],
    "impression": [r"impressions?", r"conclusions?"],
    "recommendations": [r"recommendations?", r"follow[\s-]*up\s+recommendations?"],
}

_HEADER_ALTERNATION = "|".join(
    f"(?P<{section}>{'|'.join(patterns)})"
    for section, patterns in _SECTION_HEADER_PATTERNS.items()
)
_HEADER_WITH_TEXT = re.compile(
    rf"^\s*(?:{_HEADER_ALTERNATION})\s*(?::|\s-\s|\s–\s)\s*(?P<rest>.*)$", re.IGNORECASE
)
_HEADER_ALONE = re.compile(rf"^\s*(?:{_HEADER_ALTERNATION})\s*:?\s*$", re.IGNORECASE)

# Lines that close the report body: what follows is a signature block, not
# part of the last section.
_TERMINATOR = re.compile(
    r"^\s*(?:electronically\s+signed|signed\s+by|signed\s*:|dictated\s+by|transcribed\s+by|"
    r"interpreted\s+by|reading\s+radiologist|attending\s+radiologist|radiologist\s*:|"
    r"this\s+report\s+(?:was|has\s+been)\s+(?:electronically\s+)?signed)",
    re.IGNORECASE,
)
# Page furniture that can sit inside a section that runs across pages.
_PAGE_NOISE = re.compile(
    r"^\s*(?:page\s+\d+(?:\s+of\s+\d+)?|\(?continued\)?|cont(?:inued)?\.?)\s*$"
    # MediGuide's own synthetic-sample disclaimers are not report wording.
    r"|^\s*(?:mediguide\s+synthetic\s+imaging\s+fixture|educational\s+sample\s+only\b.*)\s*$",
    re.IGNORECASE,
)

Box = tuple[float, float, float, float]


@dataclass
class ReportLine:
    page: int
    text: str
    bbox: Optional[Box] = None


@dataclass
class SectionSpan:
    section_type: str
    text: str
    line_start: int          # index of the header line in the report's lines
    line_end: int            # index of the last line that belongs to it
    page_start: int
    page_end: int
    header: str = ""         # the header as printed, e.g. "IMPRESSION:"
    lines: list[ReportLine] = field(default_factory=list)


def _header_match(text: str) -> tuple[str, str] | None:
    """(section_type, text after the header) when the line is a header."""
    for pattern in (_HEADER_ALONE, _HEADER_WITH_TEXT):
        match = pattern.match(text)
        if match:
            section = next(name for name in SECTION_TYPES if match.groupdict().get(name))
            rest = match.groupdict().get("rest") or ""
            return section, rest.strip()
    return None


def lines_from_text(text: str, page: int = 1) -> list[ReportLine]:
    return [ReportLine(page, line) for line in (text or "").splitlines() if line.strip()]


def lines_from_rows(rows: list[Any], page: int) -> list[ReportLine]:
    """Lines from positioned rows (objects with ``.text`` and ``.bbox``)."""
    return [ReportLine(page, row.text, tuple(row.bbox)) for row in rows if row.text.strip()]


def _join(lines: list[ReportLine]) -> str:
    text = "\n".join(line.text.strip() for line in lines if line.text.strip())
    return text.strip()


def find_sections(lines: list[ReportLine]) -> list[SectionSpan]:
    """Every recognized section, in report order, as a contiguous run of
    lines. A section type printed twice (an addendum, a repeated heading on
    a continuation page) keeps both passages in one section rather than
    silently dropping the second."""
    starts: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        match = _header_match(line.text)
        if match:
            starts.append((index, match[0], match[1]))
    spans: dict[str, SectionSpan] = {}
    order: list[str] = []
    for position, (start, section_type, rest) in enumerate(starts):
        stop = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        body: list[ReportLine] = []
        last = start
        for index in range(start + 1, stop):
            if _TERMINATOR.match(lines[index].text):
                break
            last = index
            if not _PAGE_NOISE.match(lines[index].text):
                body.append(lines[index])
        content_lines = ([ReportLine(lines[start].page, rest, lines[start].bbox)] if rest else []) + body
        text = _join(content_lines)
        if not text:
            continue
        header_line = lines[start]
        span_lines = [header_line] + body
        pages = [line.page for line in span_lines]
        if section_type in spans:
            existing = spans[section_type]
            existing.text = f"{existing.text}\n\n{text}"
            existing.line_end = max(existing.line_end, last)
            existing.page_end = max(existing.page_end, max(pages))
            existing.lines.extend(span_lines)
            continue
        spans[section_type] = SectionSpan(
            section_type=section_type,
            text=text,
            line_start=start,
            line_end=last,
            page_start=min(pages),
            page_end=max(pages),
            header=header_line.text.strip()[:80],
            lines=span_lines,
        )
        order.append(section_type)
    return [spans[name] for name in order]


def sections_from_ranges(lines: list[ReportLine], ranges: list[tuple[str, int, int]]) -> list[SectionSpan]:
    """Sections from reviewer-adjusted line ranges: (type, first, last line).

    The text is always the report's own lines in that range; a header at the
    start of the range is dropped from the text, nothing else changes.
    """
    spans: list[SectionSpan] = []
    for section_type, first, last in ranges:
        chosen = lines[first:last + 1]
        if not chosen:
            continue
        head = _header_match(chosen[0].text)
        # Heading labels inside the range ("IMPRESSION:") are labels, not
        # wording: they are dropped and only the text after them is kept.
        content: list[ReportLine] = []
        for line in chosen:
            if _PAGE_NOISE.match(line.text):
                continue
            match = _header_match(line.text)
            if match:
                if match[1]:
                    content.append(ReportLine(line.page, match[1], line.bbox))
                continue
            content.append(line)
        text = _join(content)
        if not text:
            continue
        pages = [line.page for line in chosen]
        spans.append(SectionSpan(section_type, text, first, last, min(pages), max(pages),
                                 chosen[0].text.strip()[:80] if head else "", list(chosen)))
    return spans


def section_regions(span: SectionSpan, page_sizes: dict[int, tuple[float, float]]) -> list[dict[str, Any]]:
    """Where on each page the section's wording sits: the union of its
    positioned lines per page. Pages without positions get no region (the
    viewer then says so instead of drawing a guess)."""
    regions: list[dict[str, Any]] = []
    by_page: dict[int, list[Box]] = {}
    for line in span.lines:
        if line.bbox is not None:
            by_page.setdefault(line.page, []).append(line.bbox)
    for page, boxes in sorted(by_page.items()):
        size = page_sizes.get(page)
        if not size:
            continue
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        regions.append({
            "page": page,
            "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
            "width": round(size[0], 2),
            "height": round(size[1], 2),
        })
    return regions


def split_report_sections(text: str) -> dict[str, str]:
    """Returns {section_type: verbatim text} for every recognized header
    found in ``text``. Only known radiology-report headers (see
    SECTION_TYPES) are recognized; everything else is left for the human
    reviewer rather than guessed at."""
    if not text or not text.strip():
        return {}
    return {span.section_type: span.text for span in find_sections(lines_from_text(text))}


# ------------------------------------------------------------ classification

# Modality words, strongest evidence first. Matched on word boundaries.
_MODALITY_PATTERNS: list[tuple[str, str]] = [
    ("pet_ct", r"pet\s*/\s*ct|pet-ct|positron\s+emission"),
    ("mri", r"mri|mr\s+(?:angiogra\w+|arthrogra\w+|of\b)|magnetic\s+resonance"),
    ("ct", r"ct|cta|computed\s+tomography|cat\s+scan"),
    ("ultrasound", r"ultrasound|ultrasonograph\w*|sonogra\w+|sonograph\w*|doppler|echograph\w*|\bus\b(?=\s+(?:of|abdomen|pelvis|renal|thyroid|breast|liver))"),
    ("mammography", r"mammogra\w+|tomosynthesis|bi-?rads"),
    ("xray", r"x-?ray|radiograph\w*|\bxr\b|\bcr\b(?=\s)|\d\s+views?\s+of"),
]

MODALITY_NAMES = {
    "xray": "X-Ray",
    "ct": "CT",
    "mri": "MRI",
    "ultrasound": "Ultrasound",
    "pet_ct": "PET/CT",
    "mammography": "Mammography",
}

_RADIOLOGY_HEADERS = {"findings", "impression", "technique", "comparison"}
_LAB_LINE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg/dl|g/dl|mmol/l|u/l|10\^3/ul|%)\s", re.IGNORECASE)

BODY_REGIONS = [
    "cervical spine", "thoracic spine", "lumbar spine", "lumbosacral spine", "spine",
    "brain", "head", "orbits", "sinuses", "neck", "thyroid",
    "chest", "lungs", "heart", "breast", "abdomen and pelvis", "abdomen", "pelvis", "liver", "kidneys", "renal",
    "gallbladder", "bladder", "prostate", "uterus", "ovaries",
    "shoulder", "elbow", "wrist", "hand", "finger", "hip", "knee", "ankle", "foot", "toe",
    "femur", "tibia", "humerus", "forearm",
]


def _first_match(pattern: str, text: str) -> Optional[re.Match]:
    return re.search(rf"(?<![a-z])(?:{pattern})(?![a-z])", text, re.IGNORECASE)


def classify_report(text: str, sections: list[SectionSpan] | None = None) -> dict[str, Any]:
    """What kind of report this reads as, with the evidence, never forced.

    ``category`` is "radiology_report" when the report has radiology
    headings, "not_radiology_report" when it reads like something else (for
    example a lab table) and "uncertain" otherwise. ``modality`` is only set
    when a modality is named; the exam line is preferred over the body text.
    """
    spans = sections if sections is not None else find_sections(lines_from_text(text))
    found = {span.section_type for span in spans}
    radiology_headers = found & _RADIOLOGY_HEADERS
    lab_lines = len(_LAB_LINE.findall(text or ""))
    if len(radiology_headers) >= 2 or ("findings" in found and "impression" in found):
        category = "radiology_report"
    elif lab_lines >= 3 and not radiology_headers:
        category = "not_radiology_report"
    else:
        category = "uncertain"

    exam_text = next((span.text for span in spans if span.section_type == "exam"), "")
    modality = None
    evidence = ""
    for source in (exam_text, (text or "")[:600], text or ""):
        if not source:
            continue
        # The modality named first in this text wins (the exam line names
        # the study; later mentions are usually comparisons).
        hits = [(match.start(), code, match.group(0)) for code, pattern in _MODALITY_PATTERNS
                if (match := _first_match(pattern, source))]
        if hits:
            _, modality, evidence = min(hits)
            break
    return {
        "category": category,
        "modality": modality,
        "modality_label": MODALITY_NAMES.get(modality or "", ""),
        "modality_evidence": evidence,
        "headers_found": sorted(found),
    }


_DETAIL_LABELS: dict[str, str] = {
    "exam_date": r"(?:date\s+of\s+(?:exam(?:ination)?|service|study|procedure)|exam(?:ination)?\s+date(?:/time)?|study\s+date|procedure\s+date|date\s+performed|service\s+date)",
    "ordering_clinician": r"(?:ordering|referring|requesting)\s+(?:physician|provider|clinician|doctor|practitioner)|ordered\s+by|referred\s+by",
    "facility": r"(?:performing\s+)?(?:facility|institution|imaging\s+center|hospital|location)",
}
_DATE_VALUE = re.compile(
    r"(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}-\d{1,2}-\d{4}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE,
)


def _labelled_value(lines: list[ReportLine], label: str) -> tuple[str, int] | None:
    pattern = re.compile(rf"^\s*(?:{label})\s*[:#-]\s*(?P<value>.+?)\s*$", re.IGNORECASE)
    for line in lines:
        match = pattern.match(line.text)
        if match and match.group("value").strip():
            return match.group("value").strip()[:160], line.page
    return None


def _iso_date(raw: str) -> str:
    from datetime import datetime

    cleaned = re.sub(r"\s+", " ", raw.replace(",", "").replace(".", "")).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def extract_report_details(lines: list[ReportLine], sections: list[SectionSpan] | None = None) -> dict[str, Any]:
    """Details the report prints with a label. Each comes with the page it
    was read from; anything not printed is simply absent (never inferred)."""
    spans = sections if sections is not None else find_sections(lines)
    details: dict[str, Any] = {}
    for key, label in _DETAIL_LABELS.items():
        found = _labelled_value(lines, label)
        if not found:
            continue
        value, page = found
        if key == "exam_date":
            date_match = _DATE_VALUE.search(value)
            iso = _iso_date(date_match.group(1)) if date_match else ""
            if not iso:
                continue
            details[key] = {"value": iso, "as_printed": value, "page": page}
        else:
            details[key] = {"value": value, "as_printed": value, "page": page}
    exam = next((span for span in spans if span.section_type == "exam"), None)
    if exam:
        first_line = exam.text.splitlines()[0].strip()
        details["study_description"] = {"value": first_line[:200], "as_printed": first_line, "page": exam.page_start}
        lowered = first_line.lower()
        region = next((name for name in BODY_REGIONS if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", lowered)), None)
        if region:
            side = re.search(r"(?<![a-z])(left|right|bilateral)(?![a-z])", lowered)
            value = f"{side.group(1).title()} {region}" if side else region.title()
            details["body_region"] = {"value": value, "as_printed": first_line, "page": exam.page_start}
    return details
