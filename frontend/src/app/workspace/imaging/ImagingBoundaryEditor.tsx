import { useEffect, useMemo, useState } from "react";
import { SECTION_LABELS, SECTION_ORDER, type ReportLineItem, type ReportSection } from "./imaging-types";

const NONE = "";

/**
 * Re-draw section boundaries over the report's own lines. Each line can
 * belong to one section (or none); a section must be one continuous block.
 * Only the report's wording can end up in a section, nothing can be typed in.
 */
export function ImagingBoundaryEditor({
  lines,
  sections,
  saving,
  onSave,
  onCancel,
}: {
  lines: ReportLineItem[];
  sections: ReportSection[];
  saving: boolean;
  onSave: (ranges: { section_type: string; line_start: number; line_end: number }[]) => void;
  onCancel: () => void;
}) {
  const initial = useMemo(() => {
    const assigned: string[] = lines.map(() => NONE);
    for (const section of sections) {
      if (section.line_start == null || section.line_end == null) continue;
      for (let index = section.line_start; index <= section.line_end && index < assigned.length; index += 1) {
        assigned[index] = section.section_type;
      }
    }
    return assigned;
  }, [lines, sections]);
  const [assigned, setAssigned] = useState<string[]>(initial);
  const [error, setError] = useState("");
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { setAssigned(initial); }, [initial]);

  function save() {
    const ranges: { section_type: string; line_start: number; line_end: number }[] = [];
    let index = 0;
    while (index < assigned.length) {
      const type = assigned[index];
      let end = index;
      while (end + 1 < assigned.length && assigned[end + 1] === type) end += 1;
      if (type !== NONE) ranges.push({ section_type: type, line_start: index, line_end: end });
      index = end + 1;
    }
    const seen = new Set<string>();
    for (const range of ranges) {
      if (seen.has(range.section_type)) {
        setError(`${SECTION_LABELS[range.section_type]} must be one continuous block of lines.`);
        return;
      }
      seen.add(range.section_type);
    }
    if (!ranges.length) {
      setError("Assign at least one line to a section.");
      return;
    }
    setError("");
    onSave(ranges);
  }

  return (
    <div className="imaging-boundary-editor" role="group" aria-label="Section boundaries">
      <p className="imaging-review-help">
        Choose which section each line of the report belongs to. Sections keep the report&apos;s exact wording, and every
        section will need reviewing again after you save.
      </p>
      <ol className="imaging-boundary-lines">
        {lines.map((line, index) => {
          const pageBreak = index === 0 || lines[index - 1].page !== line.page;
          return (
            <li key={line.index} className={assigned[index] ? `is-${assigned[index]}` : "is-none"}>
              {pageBreak && <span className="imaging-boundary-page">Page {line.page}</span>}
              <select
                aria-label={`Section for line ${index + 1}`}
                value={assigned[index]}
                onChange={(event) => {
                  const next = [...assigned];
                  next[index] = event.target.value;
                  setAssigned(next);
                }}
              >
                <option value={NONE}>Not in a section</option>
                {SECTION_ORDER.map((type) => <option key={type} value={type}>{SECTION_LABELS[type]}</option>)}
              </select>
              <span className="imaging-boundary-text">{line.text}</span>
            </li>
          );
        })}
      </ol>
      {error && <p className="imaging-edit-error" role="alert">{error}</p>}
      <div className="imaging-section-actions">
        <button type="button" className="forest-button" disabled={saving} onClick={save}>Save boundaries</button>
        <button type="button" className="quiet-button" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
