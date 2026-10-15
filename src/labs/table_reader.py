"""Read lab measurements from a PDF page using word positions.

Root cause this addresses: page text was read as a flat stream and parsed
line by line, so the parser had no idea which column a number came from. In
a table such as

    Test            Result  Flag  Reference Range  Units
    Glucose         112     H     70 - 99          mg/dL

the old parser produced a test named "Glucose 112 H 70 -" with value "99".
Here rows are rebuilt from word coordinates, and when the table has a
header row each word is assigned to its column by x-position, so a value
can only come from the Result column. Tables without a recognisable header
fall back to the strict line grammar in ``line_parser``.

Every row keeps its bounding box (PDF points, page-relative) so the review
screen can point at the exact source region. Nothing is ever repaired or
guessed: a row whose cells don't validate is returned flagged for review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.labs.line_parser import (
    _DATE_OR_TIME,
    _FLAG_WORDS,
    _NUMBER,
    _RANGE,
    _UNIT,
    ParsedMeasurement,
    is_metadata_label,
    is_unparsed_result_line,
    parse_lab_line,
)

Box = tuple[float, float, float, float]


@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    # OCR confidence (0-100) for this word; text-layer words are exact.
    confidence: float = 100.0


@dataclass
class Row:
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def bbox(self) -> Box:
        return (
            min(w.x0 for w in self.words),
            min(w.y0 for w in self.words),
            max(w.x1 for w in self.words),
            max(w.y1 for w in self.words),
        )


@dataclass
class RowMeasurement:
    measurement: ParsedMeasurement
    bbox: Box
    row: Row | None = None

    @property
    def min_confidence(self) -> float:
        return min((w.confidence for w in self.row.words), default=100.0) if self.row else 100.0


@dataclass
class UnreadRow:
    text: str
    bbox: Box


# ------------------------------------------------------------------ rows

def rows_from_words(raw_words: list[tuple]) -> list[Row]:
    """Rows from PyMuPDF's ``page.get_text("words")`` output."""
    return group_rows([Word(float(w[0]), float(w[1]), float(w[2]), float(w[3]), str(w[4])) for w in raw_words if str(w[4]).strip()])


def group_rows(words: list[Word]) -> list[Row]:
    """Group words into visual rows by vertical overlap, left to right.

    Grouping by geometry (not the text stream) keeps table cells on their
    row even when a PDF stores each cell as a separate text block, or OCR
    segments a table column by column.
    """
    words = list(words)
    words.sort(key=lambda w: ((w.y0 + w.y1) / 2, w.x0))
    rows: list[Row] = []
    for word in words:
        middle = (word.y0 + word.y1) / 2
        height = max(word.y1 - word.y0, 1.0)
        target = None
        for row in reversed(rows[-3:]):
            y0, y1 = min(w.y0 for w in row.words), max(w.y1 for w in row.words)
            if y0 - height * 0.15 <= middle <= y1 + height * 0.15:
                target = row
                break
        if target is None:
            rows.append(Row([word]))
        else:
            target.words.append(word)
    for row in rows:
        row.words.sort(key=lambda w: w.x0)
    return rows


# --------------------------------------------------------------- columns

_COLUMN_WORDS = {
    "name": {"test", "tests", "analyte", "component", "name", "description", "investigation", "parameter"},
    "value": {"result", "results", "value", "values", "observed"},
    "flag": {"flag", "flags", "abn", "abnormal", "h/l", "status"},
    "range": {"reference", "ref", "range", "normal", "interval", "ref.", "limits"},
    "unit": {"unit", "units"},
}


def _column_of(text: str) -> str | None:
    token = text.lower().strip(":()")
    for column, words in _COLUMN_WORDS.items():
        if token in words:
            return column
    return None


def detect_header(row: Row) -> dict[str, float] | None:
    """Column start positions when ``row`` is a results-table header.

    A header needs a value column plus at least two of name/range/unit/flag,
    and nothing that looks like data (no digits).
    """
    if re.search(r"\d", row.text):
        return None
    starts: dict[str, float] = {}
    for word in row.words:
        column = _column_of(word.text)
        if column and column not in starts:
            starts[column] = word.x0
    if "value" not in starts or len(starts) < 3:
        return None
    # Words before the first recognised heading belong to the name column.
    starts.setdefault("name", min(w.x0 for w in row.words))
    return starts


def _split_by_columns(row: Row, starts: dict[str, float]) -> dict[str, str]:
    """Assign each word to the column whose start is nearest on its left.

    A small slack lets right-aligned numbers that begin a little before
    their heading still land in that column.
    """
    ordered = sorted(starts.items(), key=lambda item: item[1])
    cells: dict[str, list[str]] = {name: [] for name, _ in ordered}
    for word in row.words:
        column = ordered[0][0]
        for name, x in ordered:
            if word.x0 >= x - 12:
                column = name
        cells[column].append(word.text)
    return {name: " ".join(parts).strip() for name, parts in cells.items()}


_VALUE = re.compile(rf"^(?:[<>]=?\s?)?{_NUMBER}$")
_RANGE_FULL = re.compile(rf"^{_RANGE}$", re.I)
_UNIT_FULL = re.compile(rf"^{_UNIT}$", re.I)


def measurement_from_cells(cells: dict[str, str], source_text: str) -> ParsedMeasurement | None:
    """Validate one table row's cells. None when the row isn't a result row
    (a section heading, a note, or a heading-like name with no value)."""
    name = cells.get("name", "").strip(" :-")
    raw_value = cells.get("value", "").strip()
    tokens = raw_value.split()
    # Only a comparator may be separated from its number ("< 5"). Several
    # numbers in one value cell means rows or columns ran together (OCR on
    # a small photo merged "0.9", "2", "139" into "0.92139"): never join
    # them into a value; let the row surface as unread instead.
    if len(tokens) > 1 and not (len(tokens) == 2 and tokens[0] in {"<", ">", "<=", ">="}):
        return None
    value = raw_value.replace(" ", "")
    flag = cells.get("flag", "").strip()
    reference_range = cells.get("range", "").strip()
    unit = cells.get("unit", "").strip()

    if not name or not value or sum(ch.isalpha() for ch in name) < 2:
        return None
    if is_metadata_label(name) or _DATE_OR_TIME.search(source_text):
        return None

    needs_review = False
    # A flag printed inside the result cell ("112 H") is split off, never
    # folded into the value.
    flag_in_value = re.match(rf"^((?:[<>]=?)?{_NUMBER})(HH|LL|H|L|\*)$", value, re.I)
    if flag_in_value and not flag:
        value, flag = flag_in_value.group(1), flag_in_value.group(2)
    if not _VALUE.match(value):
        # Qualitative ("Negative") or unreadable: keep it, but a person
        # must look at it.
        needs_review = True
    if reference_range and not _RANGE_FULL.match(reference_range):
        needs_review = True
    if unit and (not _UNIT_FULL.match(unit) or re.match(r"^[-/]\d", unit)):
        needs_review = True
    if flag and flag.lower() not in _FLAG_WORDS and flag not in {"A", "*"}:
        needs_review = True
    if re.search(r"\d\s*(?:-|–|to)\s*\d", name):
        # A range swallowed into the name means the columns didn't line up.
        needs_review = True

    return ParsedMeasurement(
        label=name,
        value=value,
        unit=unit,
        reference_range=reference_range,
        flag=_FLAG_WORDS.get(flag.lower(), flag.upper()),
        needs_review=needs_review,
        source_text=source_text,
    )


# ------------------------------------------------------------------ page

def read_page_rows(rows: list[Row]) -> tuple[list[RowMeasurement], list[UnreadRow]]:
    """Measurements found on one page's rows, plus rows that looked like
    results but could not be read safely (for manual review)."""
    found: list[RowMeasurement] = []
    unread: list[UnreadRow] = []
    starts: dict[str, float] | None = None
    pending_name: Row | None = None

    for row in rows:
        header = detect_header(row)
        if header:
            starts, pending_name = header, None
            continue

        if starts:
            cells = _split_by_columns(row, starts)
            has_value = bool(cells.get("value"))
            # Multi-line test name: a letters-only row continued by a row
            # whose name cell is empty. A row with numbers is never held back
            # as a name fragment (that silently dropped misaligned results).
            if not has_value and cells.get("name") and not re.search(r"\d", row.text):
                pending_name = row
                continue
            if has_value and not cells.get("name") and pending_name is not None:
                cells["name"] = " ".join(w.text for w in pending_name.words)
                merged = Row(pending_name.words + row.words)
                measurement = measurement_from_cells(cells, merged.text)
                pending_name = None
                if measurement:
                    found.append(RowMeasurement(measurement, merged.bbox, merged))
                continue
            pending_name = None
            # Cross-check: a header doesn't prove the rows are laid out in
            # its columns (a report may print "Name Value Unit Reference"
            # above plain result lines). Trust the column reading only when
            # its cells validate; otherwise prefer a clean line reading;
            # anything still uncertain stays flagged for review.
            by_column = measurement_from_cells(cells, row.text) if has_value else None
            by_line = parse_lab_line(row.text)
            if by_column and not by_column.needs_review:
                chosen = by_column
            elif by_line and not by_line.needs_review:
                chosen = by_line
            else:
                chosen = by_column or by_line
            if chosen:
                found.append(RowMeasurement(chosen, row.bbox, row))
            elif is_unparsed_result_line(row.text):
                unread.append(UnreadRow(row.text, row.bbox))
            continue

        measurement = parse_lab_line(row.text)
        if measurement:
            found.append(RowMeasurement(measurement, row.bbox, row))
        elif is_unparsed_result_line(row.text):
            unread.append(UnreadRow(row.text, row.bbox))

    return found, unread
