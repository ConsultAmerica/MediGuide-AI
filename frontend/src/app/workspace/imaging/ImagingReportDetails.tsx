import { useState } from "react";
import { AlertTriangle, ClipboardCheck } from "lucide-react";
import { MODALITY_LABELS, formatStudyDate, type ImagingStudy, type Modality } from "./imaging-types";

type DetailKey = "exam_date" | "facility" | "body_region" | "study_description" | "ordering_clinician";

const DETAIL_ROWS: { key: DetailKey; label: string; field: string | null }[] = [
  { key: "study_description", label: "Exam", field: "study_description" },
  { key: "body_region", label: "Body region", field: "body_region" },
  { key: "exam_date", label: "Exam date", field: "study_date" },
  { key: "facility", label: "Facility", field: "institution" },
  { key: "ordering_clinician", label: "Ordering clinician", field: null },
];

function studyValue(study: ImagingStudy, field: string): string {
  if (field === "study_date") return study.study_date || "";
  return String((study as unknown as Record<string, unknown>)[field] || "");
}

/**
 * What the report itself says about the study: which kind of report it
 * reads as and the details it prints with a label. Nothing here changes the
 * study unless the user picks it; the report's own reading is kept either
 * way, so the original prediction stays auditable.
 */
export function ImagingReportDetails({
  study,
  applying,
  onApply,
}: {
  study: ImagingStudy;
  applying: boolean;
  onApply: (fields: string[]) => void;
}) {
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const info = study.report_details;
  if (!info?.classification) return null;
  const { classification } = info;
  const details = info.details || {};
  const applied = info.applied || {};
  const reportModality = classification.modality;
  const mismatch = Boolean(reportModality) && reportModality !== study.modality;
  const canSwitch = mismatch && reportModality && reportModality in MODALITY_LABELS;
  const rows = DETAIL_ROWS.filter((row) => details[row.key]?.value);

  function toggle(field: string) {
    const next = new Set(picked);
    if (next.has(field)) next.delete(field); else next.add(field);
    setPicked(next);
  }

  return (
    <section className="imaging-report-details" aria-labelledby="imaging-report-details-title">
      <p className="imaging-report-kicker" id="imaging-report-details-title">
        <ClipboardCheck size={13} /> What the report says about this study
      </p>

      {classification.category === "not_radiology_report" && (
        <p className="imaging-details-warning" role="note">
          <AlertTriangle size={14} aria-hidden="true" /> This file doesn&apos;t read like a radiology report (it has no Findings or Impression headings). Check that the right document is attached.
        </p>
      )}
      {classification.category === "uncertain" && (
        <p className="imaging-details-note">MediGuide couldn&apos;t tell what kind of report this is from its headings. Review each section carefully.</p>
      )}
      {reportModality ? (
        <p className="imaging-details-note">
          Reads as a <strong>{classification.modality_label || reportModality}</strong> report
          {classification.modality_evidence ? <> (the report says “{classification.modality_evidence}”)</> : null}.
        </p>
      ) : (
        <p className="imaging-details-note">The report doesn&apos;t name the type of scan.</p>
      )}
      {mismatch && (
        <div className="imaging-details-warning" role="note">
          <AlertTriangle size={14} aria-hidden="true" />
          <span>
            This study is filed as {MODALITY_LABELS[study.modality]}, but the report reads as {classification.modality_label || reportModality}. Check which is right.
            {!canSwitch && " MediGuide doesn't organize that type separately yet, so the study keeps its current type."}
          </span>
          {canSwitch && (
            <button type="button" className="quiet-button" disabled={applying} onClick={() => onApply(["modality"])}>
              Change study type to {MODALITY_LABELS[reportModality as Modality]}
            </button>
          )}
        </div>
      )}

      {rows.length > 0 && (
        <dl className="imaging-details-list">
          {rows.map((row) => {
            const detail = details[row.key]!;
            const current = row.field ? studyValue(study, row.field) : "";
            const differs = Boolean(row.field) && current.trim().toLowerCase() !== detail.value.trim().toLowerCase();
            const wasApplied = row.field ? applied[row.field] : undefined;
            return (
              <div key={row.key}>
                <dt>{row.label}</dt>
                <dd>
                  <span>{row.key === "exam_date" ? formatStudyDate(detail.value) : detail.value}</span>
                  <small>As printed on page {detail.page}{detail.as_printed !== detail.value ? `: “${detail.as_printed}”` : ""}</small>
                  {wasApplied ? <small className="imaging-applied">Applied to this study</small> : null}
                  {row.field && differs && !wasApplied ? (
                    <label className="imaging-detail-pick">
                      <input type="checkbox" checked={picked.has(row.field)} onChange={() => toggle(row.field!)} />
                      Use for this study{current ? ` (now: ${row.key === "exam_date" ? formatStudyDate(current) : current})` : ""}
                    </label>
                  ) : null}
                </dd>
              </div>
            );
          })}
        </dl>
      )}
      {picked.size > 0 && (
        <button
          type="button"
          className="forest-button"
          disabled={applying}
          onClick={() => {
            onApply(Array.from(picked));
            setPicked(new Set());
          }}
        >
          Use selected details for this study
        </button>
      )}
    </section>
  );
}
