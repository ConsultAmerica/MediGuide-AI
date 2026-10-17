"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Check, ChevronLeft, ChevronRight, FileText, Maximize2, RotateCw, Undo2, ZoomIn, ZoomOut } from "lucide-react";
import { AuthImage } from "../_components/AuthImage";
import { ConfirmDialog } from "../polish-ui";
import {
  DOC_CONFIDENCE_LABELS,
  DOC_STATUS_LABELS,
  REVIEWABLE_KEYS,
  isBulkConfirmable,
  type DocField,
  type DocPage,
  type DocState,
  type DraftSaveStatus,
  type FieldReviewDecision,
  type ReviewablePatch,
} from "../_state/workspace-shared";

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.25;
const UNREAD_LINE_LABEL = "Unread line";

const DECISION_LABELS: Record<FieldReviewDecision, string> = {
  unverified: "Unverified",
  confirmed: "Confirmed",
  corrected: "Corrected",
  rejected: "Rejected",
};

type EditDraft = { id: string; values: Record<(typeof REVIEWABLE_KEYS)[number], string>; error: string };

function decisionOf(review: Record<string, FieldReviewDecision>, field: DocField): FieldReviewDecision {
  return review[field.field_id] || "unverified";
}

function isUnreadLine(field: DocField) {
  return field.confidence === "could_not_read" || field.label === UNREAD_LINE_LABEL;
}

/** Places a field's recorded source region on the page, in percent of the
 * page's own coordinate space. Null when there is nothing honest to draw. */
function regionStyle(field: DocField | undefined, page: DocPage | undefined): CSSProperties | null {
  const box = field?.source_bbox;
  const width = page?.width || 0;
  const height = page?.height || 0;
  if (!box || box.length !== 4 || width <= 0 || height <= 0) return null;
  const [x0, y0, x1, y1] = box;
  if (!(x1 > x0 && y1 > y0)) return null;
  // A little breathing room so the outline doesn't sit on the glyphs.
  const padX = width * 0.006;
  const padY = height * 0.004;
  const left = Math.max(0, x0 - padX);
  const top = Math.max(0, y0 - padY);
  const right = Math.min(width, x1 + padX);
  const bottom = Math.min(height, y1 + padY);
  return {
    left: `${(left / width) * 100}%`,
    top: `${(top / height) * 100}%`,
    width: `${((right - left) / width) * 100}%`,
    height: `${((bottom - top) / height) * 100}%`,
  };
}

export function DocumentReview({
  apiUrl, docState, docFields, docConfirmed, docSelectedPage, setDocSelectedPage,
  highlightedFieldId, setHighlightedFieldId, fieldReviewState, draftStatus,
  previewZoom, setPreviewZoom, docReviewChecked, setDocReviewChecked, loading,
  onSaveCorrection, onDecide, onUndo, onConfirm, afterFields, emptyFields,
}: {
  apiUrl: string;
  docState: DocState;
  docFields: DocField[];
  docConfirmed: boolean;
  docSelectedPage: number;
  setDocSelectedPage: (value: number) => void;
  highlightedFieldId: string | null;
  setHighlightedFieldId: (value: string | null) => void;
  fieldReviewState: Record<string, FieldReviewDecision>;
  draftStatus: DraftSaveStatus;
  previewZoom: number;
  setPreviewZoom: (value: number) => void;
  docReviewChecked: boolean;
  setDocReviewChecked: (value: boolean) => void;
  loading: string;
  onSaveCorrection: (fieldId: string, patch: ReviewablePatch) => void;
  onDecide: (fieldIds: string[], decision: "confirmed" | "rejected") => void;
  onUndo: (fieldId: string) => void;
  onConfirm: () => void;
  afterFields?: ReactNode;
  /** Shown in place of the review when nothing was extracted. */
  emptyFields?: ReactNode;
}) {
  // On narrow screens the page and the values are tabs; both stay mounted so
  // zoom, scroll and edits survive switching between them.
  const [pane, setPane] = useState<"document" | "fields">("fields");
  // Rotation is for viewing only and belongs to the page being looked at.
  const [rotated, setRotated] = useState({ page: "", degrees: 0 });
  const [editing, setEditing] = useState<EditDraft | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  const regionRef = useRef<HTMLSpanElement>(null);

  const pageCount = Math.max(1, docState.page_count);
  const page = docState.pages.find((item) => item.page_number === docSelectedPage) || docState.pages[0];
  const pageWidth = page?.width || 0;
  const pageHeight = page?.height || 0;
  const hasSize = pageWidth > 0 && pageHeight > 0;
  const pageKey = `${docState.document_id}:${docSelectedPage}`;
  const rotation = rotated.page === pageKey ? rotated.degrees : 0;
  const quarterTurn = rotation % 180 !== 0;
  const selected = docFields.find((field) => field.field_id === highlightedFieldId);
  const selectedOnPage = selected && selected.page_number === docSelectedPage ? selected : undefined;
  const region = regionStyle(selectedOnPage, page);

  const reviewedCount = docFields.filter((field) => decisionOf(fieldReviewState, field) !== "unverified").length;
  const undecided = docFields.length - reviewedCount;
  const keptCount = docFields.filter((field) => decisionOf(fieldReviewState, field) !== "rejected").length;
  const bulkEligible = docFields.filter((field) => decisionOf(fieldReviewState, field) === "unverified" && isBulkConfirmable(field));
  const pageNumbers = Array.from(new Set(docFields.map((field) => field.page_number))).sort((a, b) => a - b);
  const selectedIndex = docFields.findIndex((field) => field.field_id === highlightedFieldId);
  const remainingUndecided = docFields.some((field) => decisionOf(fieldReviewState, field) === "unverified");

  // Bring the highlighted region into view inside the viewer (not the window).
  useEffect(() => {
    const canvas = canvasRef.current;
    const target = regionRef.current;
    if (!canvas || !target) return;
    const frame = window.requestAnimationFrame(() => {
      const outer = canvas.getBoundingClientRect();
      const box = target.getBoundingClientRect();
      canvas.scrollBy({
        top: box.top - outer.top - (outer.height - box.height) / 2,
        left: box.left - outer.left - (outer.width - box.width) / 2,
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [highlightedFieldId, docSelectedPage, previewZoom, rotation]);

  const closeBulk = useCallback(() => setBulkOpen(false), []);

  function selectField(field: DocField, options: { showPage?: boolean; focusCard?: boolean } = {}) {
    setHighlightedFieldId(field.field_id);
    if (field.page_number !== docSelectedPage) setDocSelectedPage(field.page_number);
    if (options.showPage) setPane("document");
    if (options.focusCard) {
      const card = document.getElementById(`review-field-${field.field_id}`);
      if (card) {
        card.focus({ preventScroll: true });
        const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        card.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
      }
    }
  }

  function goPrevious() {
    const index = selectedIndex <= 0 ? 0 : selectedIndex - 1;
    if (docFields[index]) selectField(docFields[index], { focusCard: true });
  }

  function goNextUnreviewed() {
    const total = docFields.length;
    for (let step = 1; step <= total; step += 1) {
      const field = docFields[(Math.max(selectedIndex, -1) + step + total) % total];
      if (decisionOf(fieldReviewState, field) === "unverified") {
        selectField(field, { focusCard: true });
        return;
      }
    }
  }

  function startEdit(field: DocField) {
    selectField(field);
    setEditing({
      id: field.field_id,
      values: { label: field.label, value: field.value, unit: field.unit, reference_range: field.reference_range },
      error: "",
    });
  }

  function saveEdit(field: DocField) {
    if (!editing) return;
    const values = {
      label: editing.values.label.trim(),
      value: editing.values.value.trim(),
      unit: editing.values.unit.trim(),
      reference_range: editing.values.reference_range.trim(),
    };
    if (!values.label || values.label === UNREAD_LINE_LABEL) {
      setEditing({ ...editing, error: "Enter the test name as it appears on the page." });
      return;
    }
    if (!values.value) {
      setEditing({ ...editing, error: "Enter the value as it appears on the page, or reject this item." });
      return;
    }
    const patch: ReviewablePatch = { value: values.value };
    if (field.status !== "not_applicable") {
      patch.unit = values.unit;
      patch.reference_range = values.reference_range;
    }
    if (isUnreadLine(field)) patch.label = values.label;
    onSaveCorrection(field.field_id, patch);
    setEditing(null);
  }

  function setEditValue(key: (typeof REVIEWABLE_KEYS)[number], value: string) {
    setEditing((current) => (current ? { ...current, values: { ...current.values, [key]: value }, error: "" } : current));
  }

  const frameStyle: CSSProperties = hasSize
    ? { width: `${previewZoom * 100}%`, aspectRatio: quarterTurn ? `${pageHeight} / ${pageWidth}` : `${pageWidth} / ${pageHeight}` }
    : { width: `${previewZoom * 100}%` };
  // For a quarter turn the page is laid out in the frame's swapped box and
  // rotated about its centre, so the frame (and its scroll area) stays true.
  const pageStyle: CSSProperties = hasSize
    ? quarterTurn
      ? { width: `${(pageHeight / pageWidth) * 100}%`, height: `${(pageWidth / pageHeight) * 100}%`, transform: `translate(-50%, -50%) rotate(${rotation}deg)` }
      : { width: "100%", height: "100%", transform: `translate(-50%, -50%) rotate(${rotation}deg)` }
    : {};

  let viewerNote: string;
  if (!selectedOnPage) {
    viewerNote = selected
      ? `The selected value is on page ${selected.page_number}.`
      : "Select a value to see where it was read on the page.";
  } else if (region) {
    viewerNote = `Outlined: where “${selectedOnPage.label}” was read. Check it against the page.`;
  } else {
    viewerNote = `No position was recorded for “${selectedOnPage.label}”. Find it on the page yourself before confirming.`;
  }

  return (
    <section className="review-workspace" aria-label="Document review">
      <div className="review-tabs" role="tablist" aria-label="Review panes">
        <button type="button" role="tab" id="review-tab-document" aria-controls="review-pane-document" aria-selected={pane === "document"} className={pane === "document" ? "is-active" : ""} onClick={() => setPane("document")}>
          Original document
        </button>
        <button type="button" role="tab" id="review-tab-fields" aria-controls="review-pane-fields" aria-selected={pane === "fields"} className={pane === "fields" ? "is-active" : ""} onClick={() => setPane("fields")}>
          Extracted information
          {!docConfirmed && docFields.length > 0 && <span className="review-tab-count">{reviewedCount}/{docFields.length}</span>}
        </button>
      </div>

      <div className="review-split" data-pane={pane}>
        <div className="review-viewer" id="review-pane-document" role="tabpanel" aria-labelledby="review-tab-document">
          <p className="panel-kicker">ORIGINAL REPORT · PAGE {docSelectedPage}</p>
          <div className="review-viewer-toolbar" aria-label="Page controls">
            <div className="review-tool-group">
              <button type="button" className="review-tool" aria-label="Previous page" disabled={docSelectedPage <= 1} onClick={() => setDocSelectedPage(Math.max(1, docSelectedPage - 1))}><ChevronLeft size={16} /></button>
              <span className="review-tool-label" aria-live="polite">Page {docSelectedPage} of {pageCount}</span>
              <button type="button" className="review-tool" aria-label="Next page" disabled={docSelectedPage >= pageCount} onClick={() => setDocSelectedPage(Math.min(pageCount, docSelectedPage + 1))}><ChevronRight size={16} /></button>
            </div>
            <div className="review-tool-group">
              <button type="button" className="review-tool" aria-label="Zoom out" disabled={previewZoom <= ZOOM_MIN} onClick={() => setPreviewZoom(Math.max(ZOOM_MIN, previewZoom - ZOOM_STEP))}><ZoomOut size={16} /></button>
              <span className="review-tool-label mg-num">{Math.round(previewZoom * 100)}%</span>
              <button type="button" className="review-tool" aria-label="Zoom in" disabled={previewZoom >= ZOOM_MAX} onClick={() => setPreviewZoom(Math.min(ZOOM_MAX, previewZoom + ZOOM_STEP))}><ZoomIn size={16} /></button>
              <button type="button" className="review-tool is-text" onClick={() => setPreviewZoom(1)}><Maximize2 size={14} /> Fit width</button>
              <button type="button" className="review-tool is-text" disabled={!hasSize} title={hasSize ? undefined : "Rotation isn't available for this page"} onClick={() => setRotated({ page: pageKey, degrees: (rotation + 90) % 360 })}><RotateCw size={14} /> Rotate</button>
            </div>
          </div>

          <div className="review-canvas" ref={canvasRef} tabIndex={0} aria-label={`Page ${docSelectedPage} of the original document`}>
            {page?.preview_url ? (
              <div className={hasSize ? "review-page-frame has-size" : "review-page-frame"} style={frameStyle}>
                <div className="review-page" style={pageStyle}>
                  <AuthImage className="review-page-image" src={`${apiUrl}${page.preview_url}`} alt={`Page ${docSelectedPage} of ${docState.filename}`} />
                  {region && <span ref={regionRef} className="review-region" style={region} aria-hidden="true" />}
                </div>
              </div>
            ) : (
              <div className="doc-preview-placeholder"><FileText size={38} /><span>Page {docSelectedPage} preview</span></div>
            )}
          </div>
          <p className="review-viewer-note" aria-live="polite">{viewerNote}</p>
          <button type="button" className="quiet-button review-back-to-fields" onClick={() => setPane("fields")}>Back to extracted information</button>
        </div>

        <div className="review-panel extracted-fields doc-fields" id="review-pane-fields" role="tabpanel" aria-labelledby="review-tab-fields">
          <p className="eyebrow">{docConfirmed ? "CONFIRMED" : "VERIFICATION"}</p>
          <h3 className="doc-fields-heading">Extracted lab information</h3>
          {docFields.length > 0 && (
            <p className="doc-fields-support">
              {docConfirmed
                ? "These values were reviewed and confirmed."
                : "Check each value against the page, then confirm, correct or reject it. Nothing enters your records until you confirm the review."}
            </p>
          )}

          {!docConfirmed && docFields.length > 0 && (
            <div className="review-toolbar">
              <div className="review-progress-block">
                <p className="review-progress">{reviewedCount} of {docFields.length} reviewed</p>
                <div className="review-progress-track" role="progressbar" aria-label="Review progress" aria-valuemin={0} aria-valuemax={docFields.length} aria-valuenow={reviewedCount}>
                  <span style={{ width: `${(reviewedCount / docFields.length) * 100}%` }} />
                </div>
                <p className={`review-draft-status is-${draftStatus}`} role="status">
                  {draftStatus === "saving" && "Saving progress…"}
                  {draftStatus === "saved" && "Progress saved. You can leave and come back."}
                  {draftStatus === "error" && "Progress couldn't be saved. Your decisions are still on this page."}
                </p>
              </div>
              <div className="review-toolbar-actions">
                <button type="button" className="quiet-button" disabled={selectedIndex <= 0} onClick={goPrevious}><ChevronLeft size={15} /> Previous</button>
                <button type="button" className="quiet-button" disabled={!remainingUndecided} onClick={goNextUnreviewed}>Next unreviewed <ChevronRight size={15} /></button>
                {bulkEligible.length > 0 && (
                  <button type="button" className="quiet-button review-bulk" onClick={() => setBulkOpen(true)}>
                    <Check size={15} /> Confirm clearly read values ({bulkEligible.length})
                  </button>
                )}
              </div>
            </div>
          )}

          {docFields.length === 0 && (emptyFields ?? <p className="doc-fields-empty">No information was found in this document.</p>)}

          {pageNumbers.map((pageNumber) => (
            <div key={pageNumber} className="review-page-group">
              {pageCount > 1 && <p className="review-page-heading">Page {pageNumber}</p>}
              {docFields.filter((field) => field.page_number === pageNumber).map((field) => {
                const decision = docConfirmed ? "confirmed" : decisionOf(fieldReviewState, field);
                const isEditing = editing?.id === field.field_id;
                const flagged = field.status === "flagged_high_on_report" || field.status === "flagged_low_on_report";
                const changedFromExtraction = field.extracted && (field.extracted.value !== field.value || field.extracted.unit !== field.unit || field.extracted.reference_range !== field.reference_range || field.extracted.label !== field.label);
                return (
                  <div
                    key={field.field_id}
                    id={`review-field-${field.field_id}`}
                    tabIndex={-1}
                    className={`doc-field-row review-field status-${field.status} decision-${decision}${highlightedFieldId === field.field_id ? " field-highlighted" : ""}`}
                    onClick={() => { if (highlightedFieldId !== field.field_id) selectField(field); }}
                  >
                    <div className="doc-field-label">
                      <strong>{field.label}</strong>
                      <span className={`confidence-pill confidence-${field.confidence}`}>{DOC_CONFIDENCE_LABELS[field.confidence]}</span>
                      <span className={`status-chip review-decision decision-${decision}`}>{DECISION_LABELS[decision]}</span>
                      {flagged && DOC_STATUS_LABELS[field.status] ? <span className={`status-pill status-pill-${field.status}`}>{DOC_STATUS_LABELS[field.status]}</span> : null}
                    </div>
                    {field.source_text && <p className="doc-field-source"><span>On the report</span><code>{field.source_text}</code></p>}
                    {changedFromExtraction && field.extracted && (
                      <p className="doc-field-original">Originally read as <code>{[field.extracted.label, field.extracted.value, field.extracted.unit, field.extracted.reference_range].filter(Boolean).join(" · ")}</code></p>
                    )}
                    {field.confidence === "could_not_read" && decision === "unverified" && (
                      <p className="doc-field-unread">MediGuide couldn&apos;t read this line reliably, so nothing was filled in. Check it against the page, then reject it or enter the details yourself.</p>
                    )}

                    {isEditing && editing ? (
                      <form className="review-edit" onSubmit={(event) => { event.preventDefault(); saveEdit(field); }}>
                        <div className={field.status === "not_applicable" ? "doc-field-inputs is-date" : "doc-field-inputs"}>
                          {isUnreadLine(field) && <label className="is-wide">Test name<input value={editing.values.label === UNREAD_LINE_LABEL ? "" : editing.values.label} onChange={(event) => setEditValue("label", event.target.value)} autoFocus /></label>}
                          {field.status === "not_applicable" ? (
                            <label>{field.label}<input value={editing.values.value} onChange={(event) => setEditValue("value", event.target.value)} autoFocus={!isUnreadLine(field)} /></label>
                          ) : (
                            <>
                              <label>Value<input className="mg-num" inputMode="decimal" value={editing.values.value} onChange={(event) => setEditValue("value", event.target.value)} autoFocus={!isUnreadLine(field)} /></label>
                              <label>Unit<input value={editing.values.unit} onChange={(event) => setEditValue("unit", event.target.value)} /></label>
                              <label>Reference range<input className="mg-num" value={editing.values.reference_range} onChange={(event) => setEditValue("reference_range", event.target.value)} /></label>
                            </>
                          )}
                        </div>
                        {editing.error && <p className="review-edit-error" role="alert">{editing.error}</p>}
                        <div className="field-review-actions">
                          <button type="submit" className="forest-button">Save correction</button>
                          <button type="button" className="quiet-button" onClick={() => setEditing(null)}>Cancel edit</button>
                        </div>
                      </form>
                    ) : field.status === "not_applicable" ? (
                      <dl className="doc-field-values is-date">
                        <div><dt>Date</dt><dd className="mg-num">{field.value || "—"}</dd></div>
                      </dl>
                    ) : (
                      <dl className="doc-field-values">
                        <div><dt>Value</dt><dd className="mg-num">{field.value || "—"}</dd></div>
                        <div><dt>Unit</dt><dd>{field.unit || "—"}</dd></div>
                        <div><dt>Reference range</dt><dd className="mg-num">{field.reference_range || "—"}</dd></div>
                      </dl>
                    )}

                    {!docConfirmed && !isEditing && (
                      <div className="field-review-actions">
                        {decision === "unverified" ? (
                          <>
                            <button type="button" className="quiet-button" disabled={!field.value.trim()} title={field.value.trim() ? undefined : "Nothing was read here. Edit it or reject it."} onClick={() => onDecide([field.field_id], "confirmed")}>Confirm</button>
                            <button type="button" className="quiet-button" onClick={() => startEdit(field)}>Edit</button>
                            <button type="button" className="quiet-button" onClick={() => onDecide([field.field_id], "rejected")}>Reject</button>
                          </>
                        ) : (
                          <>
                            {decision !== "rejected" && <button type="button" className="quiet-button" onClick={() => startEdit(field)}>Edit</button>}
                            <button type="button" className="quiet-button" onClick={() => onUndo(field.field_id)}><Undo2 size={14} /> Undo</button>
                          </>
                        )}
                        <button type="button" className="quiet-button review-view-on-page" onClick={() => selectField(field, { showPage: true })}>View on page</button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}

          {/* Nothing to confirm when nothing was extracted — the gate could never open. */}
          {!docConfirmed && docFields.length > 0 && (
            <div className="confirm-gate">
              {undecided > 0 && <p className="confirm-gate-note">{undecided} {undecided === 1 ? "value still needs" : "values still need"} a decision. Confirm, correct or reject each one.</p>}
              {undecided === 0 && keptCount === 0 && docFields.length > 0 && <p className="confirm-gate-note">Every value was rejected. Keep at least one to confirm this report.</p>}
              <label className="confirm"><input type="checkbox" checked={docReviewChecked} onChange={(event) => setDocReviewChecked(event.target.checked)} /> I reviewed the names, values, units, dates, and reference ranges above.</label>
              <button className="forest-button" disabled={!docReviewChecked || undecided > 0 || keptCount === 0 || Boolean(loading)} onClick={onConfirm}>Confirm reviewed items <Check size={16} /></button>
            </div>
          )}

          {afterFields}
        </div>
      </div>

      <ConfirmDialog
        open={bulkOpen}
        title={`Confirm ${bulkEligible.length} clearly read ${bulkEligible.length === 1 ? "value" : "values"}?`}
        body={`These were read from the document's own text, were clearly visible, and have a recorded position on the page. Confirm them only if you have checked them against the page. ${undecided - bulkEligible.length > 0 ? `${undecided - bulkEligible.length} other ${undecided - bulkEligible.length === 1 ? "value still needs" : "values still need"} your individual review.` : ""}`.trim()}
        confirmLabel={`Confirm ${bulkEligible.length} ${bulkEligible.length === 1 ? "value" : "values"}`}
        onConfirm={() => { onDecide(bulkEligible.map((field) => field.field_id), "confirmed"); setBulkOpen(false); }}
        onCancel={closeBulk}
      />
    </section>
  );
}
