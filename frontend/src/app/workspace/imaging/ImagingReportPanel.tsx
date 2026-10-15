import { useState } from "react";
import { Check, FileText, ListTree, Undo2, X } from "lucide-react";
import { MODALITY_LABELS, SECTION_LABELS, SECTION_ORDER, type ImagingStudy, type ReportSection } from "./imaging-types";

type Decision = "confirmed" | "rejected" | "unverified";

const METHOD_NOTES: Record<string, string> = {
  tesseract_ocr: "Read from a scan by text recognition. Check every word against the page.",
  vision_ocr: "Read by the AI fallback because the text couldn't be read directly. Check every word against the page.",
};

function pagesLabel(section: ReportSection) {
  const end = section.page_end || section.page_number;
  return end > section.page_number ? `Pages ${section.page_number}–${end}` : `Page ${section.page_number}`;
}

/**
 * The verification workflow, one section at a time. Every decision is saved
 * as it is made, so a review can be left and resumed. The radiologist's
 * wording is always shown as extracted; a correction is shown separately
 * and never replaces it. Only sections actually present in `sections`
 * render: this list is never padded with guessed sections for types the
 * extractor didn't find (a safety property, not an incidental gap).
 */
export function ImagingReportPanel({
  study,
  sections,
  busySection,
  activeSection,
  onDecide,
  onViewSourcePage,
  onSelectSection,
  onOpenTerminology,
  canAdjustBoundaries,
  onAdjustBoundaries,
}: {
  study: ImagingStudy;
  sections: ReportSection[];
  busySection: string | null;
  activeSection: string | null;
  onDecide: (sectionType: string, decision: Decision, text?: string) => Promise<boolean>;
  onViewSourcePage: (section: ReportSection) => void;
  onSelectSection: (section: ReportSection) => void;
  onOpenTerminology: (term: string, sourceExcerpt: string) => void;
  canAdjustBoundaries: boolean;
  onAdjustBoundaries: () => void;
}) {
  const [editing, setEditing] = useState<{ type: string; text: string; error: string } | null>(null);
  const orderedSections = SECTION_ORDER.map((type) => sections.find((s) => s.section_type === type)).filter(
    (s): s is ReportSection => Boolean(s),
  );
  const decided = orderedSections.filter((s) => s.verification_status !== "unverified").length;
  const anyDecided = decided > 0;

  if (orderedSections.length === 0) {
    return <p className="imaging-empty-note">No recognized report sections were extracted from this file yet.</p>;
  }

  async function saveCorrection(section: ReportSection) {
    if (!editing) return;
    const text = editing.text.trim();
    if (!text) {
      setEditing({ ...editing, error: "A section can't be empty. Reject it instead." });
      return;
    }
    if (await onDecide(section.section_type, "confirmed", text)) setEditing(null);
  }

  return (
    <div className="imaging-report-panel">
      <p className="imaging-report-kicker">
        <FileText size={13} /> From your report
      </p>

      <div className="imaging-review-head">
        <p className="imaging-review-progress" role="status" aria-live="polite">
          {decided} of {orderedSections.length} sections reviewed
        </p>
        {canAdjustBoundaries && (
          <button
            type="button"
            className="quiet-button"
            disabled={anyDecided}
            title={anyDecided ? "Undo the confirmed or rejected sections first" : undefined}
            onClick={onAdjustBoundaries}
          >
            <ListTree size={14} /> Adjust section boundaries
          </button>
        )}
      </div>
      <p className="imaging-review-help">
        Check each section against the page, then confirm, correct or reject it. Decisions are saved as you go.
      </p>

      {orderedSections.map((section) => {
        const label = SECTION_LABELS[section.section_type] || section.section_type;
        const status = section.verification_status;
        const corrected = status === "confirmed" && section.section_text !== section.original_text;
        const isEditing = editing?.type === section.section_type;
        const busy = busySection === section.section_type;
        const chip = corrected ? "Corrected" : status === "confirmed" ? "Confirmed" : status === "rejected" ? "Rejected" : "Unverified";
        return (
          <div
            key={section.section_id}
            role="group"
            aria-label={label}
            className={`imaging-section-block status-${status}${activeSection === section.section_type ? " is-active" : ""}`}
          >
            <div className="imaging-section-header">
              <button type="button" className="imaging-section-title" onClick={() => onSelectSection(section)}>
                {label}
              </button>
              <span className={`imaging-section-status imaging-section-status-${status === "unverified" ? "unreviewed" : "reviewed"} is-${chip.toLowerCase()}`}>
                {chip}
              </span>
            </div>
            <p className="imaging-section-meta">
              {MODALITY_LABELS[study.modality]} report · {pagesLabel(section)}
              {section.boundary_adjusted ? " · boundaries adjusted by you" : ""}
            </p>
            {METHOD_NOTES[section.extraction_method || ""] && (
              <p className="imaging-method-note">{METHOD_NOTES[section.extraction_method || ""]}</p>
            )}

            <div className="imaging-original-extraction">
              <small>{corrected ? "Original extraction · the radiologist's wording" : "The radiologist's wording"}</small>
              <p>{section.original_text}</p>
            </div>
            {corrected && (
              <div className="imaging-corrected-wording">
                <small>Your corrected version</small>
                <p>{section.section_text}</p>
              </div>
            )}

            {isEditing && editing ? (
              <div className="imaging-section-edit">
                <textarea
                  id={`imaging-section-${section.section_id}`}
                  aria-label={label}
                  value={editing.text}
                  autoFocus
                  onChange={(event) => setEditing({ ...editing, text: event.target.value, error: "" })}
                />
                {editing.error && <p className="imaging-edit-error" role="alert">{editing.error}</p>}
                <div className="imaging-section-actions">
                  <button type="button" className="forest-button" disabled={busy} onClick={() => void saveCorrection(section)}>
                    Save correction
                  </button>
                  <button type="button" className="quiet-button" onClick={() => setEditing(null)}>Cancel edit</button>
                </div>
              </div>
            ) : (
              <div className="imaging-section-actions">
                {status === "unverified" ? (
                  <>
                    <button type="button" className="quiet-button" disabled={busy} onClick={() => void onDecide(section.section_type, "confirmed")}>
                      <Check size={14} /> Confirm
                    </button>
                    <button type="button" className="quiet-button" disabled={busy} onClick={() => setEditing({ type: section.section_type, text: section.section_text, error: "" })}>
                      Edit
                    </button>
                    <button type="button" className="quiet-button" disabled={busy} onClick={() => void onDecide(section.section_type, "rejected")}>
                      <X size={14} /> Reject
                    </button>
                  </>
                ) : (
                  <button type="button" className="quiet-button" disabled={busy} onClick={() => void onDecide(section.section_type, "unverified")}>
                    <Undo2 size={14} /> Undo
                  </button>
                )}
                <button type="button" className="quiet-button" onClick={() => onViewSourcePage(section)}>
                  View source page
                </button>
                <button
                  type="button"
                  className="quiet-button"
                  onClick={() => onOpenTerminology("", (section.section_text || "").split(/\s+/).slice(0, 24).join(" "))}
                >
                  Understand terminology
                </button>
              </div>
            )}
          </div>
        );
      })}

      {decided === orderedSections.length ? (
        <p className="imaging-next-step" role="status">
          {orderedSections.some((s) => s.verification_status === "confirmed")
            ? "Every section has a decision. Next: verify structured findings below so Overview can summarize what you accepted."
            : "Every section was rejected, so nothing from this report is verified. Undo a section to keep it."}
        </p>
      ) : null}
    </div>
  );
}
