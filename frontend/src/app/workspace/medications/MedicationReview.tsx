"use client";

import { useState } from "react";
import { AlertTriangle, Check, FileText, Pencil, RotateCcw, X } from "lucide-react";
import { apiFetch } from "../../../lib/auth";
import { parseApiError } from "../../../lib/api-error";
import { AuthImage } from "../_components/AuthImage";
import type { MedEntry, MedField, MedMatch, MedState } from "../_state/workspace-shared";

const NOTE_TEXT: Record<string, string> = {
  missing_directions: "No directions were found on this label. Nothing has been filled in for how to take it.",
  ambiguous_directions: "The directions are unclear (for example “as directed”). Check them with your pharmacist or prescriber.",
  risky_abbreviation: "The directions use an abbreviation that is easy to misread (such as QD or QOD). Ask your pharmacist what it means.",
  dose_range: "The directions give a range (for example 1-2 tablets), not a single amount.",
  frequency_not_stated: "The directions don't say how often to take it.",
  several_strengths: "More than one strength is printed on the medication line. Check which one applies.",
  ai_read: "This label was read by the AI fallback because its text couldn't be read directly. Check every detail against the label.",
  low_confidence_text: "Some of this label was hard to read. Check every detail against the label.",
};

const FLAG_TEXT: Record<string, string> = {
  from_directions: "From the directions",
  shared_detail: "Printed once for the whole list",
  ai_read: "Read by AI",
  may_be_prescriber: "May be the prescriber",
  second_name_in_brackets: "Second name in brackets, kept as printed",
  dose_range: "A range",
  ambiguous_directions: "Unclear",
  risky_abbreviation: "Easy-to-misread abbreviation",
  several_strengths: "Several strengths printed",
};

const CONFIDENCE_TEXT: Record<string, string> = {
  clearly_visible: "Clearly visible",
  needs_review: "Needs review",
  could_not_read: "Could not read",
  not_found: "Not on the label",
};

const READ_NOTES: Record<string, string> = {
  ocr: "Read from the photo or scan by text recognition on this device. Check every detail against the label.",
  vision: "The label's text couldn't be read directly, so the AI fallback read it. Every detail needs checking.",
  typed_ai: "MediGuide couldn't find a medication in the typed text, so the AI fallback read it. Every detail needs checking.",
};

// The key details shown first; the rest follow.
const PRIMARY = ["medication_name", "strength", "dosage_form", "directions", "dose", "frequency", "route"];

function fieldValue(entry: MedEntry, key: string) {
  return entry.fields.find((field) => field.key === key)?.value || "";
}

function MatchPanel({ matches, acknowledged, onToggle, disabled }: {
  matches: MedMatch[];
  acknowledged: Set<string>;
  onToggle: (recordId: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="med-matches" role="note">
      {matches.map((match) => (
        <div key={match.record_id} className={`med-match is-${match.kind}`}>
          <p className="med-match-title">
            <AlertTriangle size={14} aria-hidden="true" />
            {match.kind === "conflict"
              ? `You already have a ${match.medication_name} record with different details.`
              : `You may already have this medication: a ${match.medication_name} record with the same details.`}
          </p>
          <p className="med-match-source">
            Existing record from {match.source}
            {match.confirmed_at ? `, added ${new Date(match.confirmed_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}` : ""}.
          </p>
          {match.differences.length > 0 && (
            <table className="med-match-table">
              <caption className="sr-only">Differences between this label and the existing record</caption>
              <thead><tr><th scope="col">Detail</th><th scope="col">This label</th><th scope="col">Existing record</th></tr></thead>
              <tbody>
                {match.differences.map((difference) => (
                  <tr key={difference.field}>
                    <th scope="row">{difference.label}</th>
                    <td>{difference.this_label}</td>
                    <td>{difference.existing_record}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="med-match-note">
            MediGuide keeps both records and doesn&apos;t decide which one is current. Check with your pharmacist or prescriber.
          </p>
          <label className="med-match-ack">
            <input type="checkbox" checked={acknowledged.has(match.record_id)} disabled={disabled} onChange={() => onToggle(match.record_id)} />
            I compared this label with the existing record
          </label>
        </div>
      ))}
    </div>
  );
}

function EntryCard({ entry, busy, onConfirm, onReject, onRestore }: {
  entry: MedEntry;
  busy: boolean;
  onConfirm: (entry: MedEntry, fields: MedField[], acknowledged: string[]) => Promise<boolean>;
  onReject: (entry: MedEntry) => void;
  onRestore: (entry: MedEntry) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [checked, setChecked] = useState(false);
  const [acknowledged, setAcknowledged] = useState<Set<string>>(new Set());
  const name = fieldValue(entry, "medication_name") || "Unnamed medication";
  const strength = fieldValue(entry, "strength");
  const decided = entry.decision !== "unverified";
  const ordered = [...PRIMARY.map((key) => entry.fields.find((field) => field.key === key)), ...entry.fields.filter((field) => !PRIMARY.includes(field.key))]
    .filter((field): field is MedField => Boolean(field));
  const currentValue = (field: MedField) => (editing ? (draft[field.key] ?? field.value) : field.value);
  const allAcknowledged = entry.matches.every((match) => acknowledged.has(match.record_id));
  const nameMissing = !(editing ? (draft.medication_name ?? fieldValue(entry, "medication_name")) : fieldValue(entry, "medication_name")).trim();

  async function confirm() {
    const fields = entry.fields.map((field) => ({ ...field, value: (draft[field.key] ?? field.value).trim() }));
    if (await onConfirm(entry, fields, Array.from(acknowledged))) {
      setEditing(false);
      setDraft({});
    }
  }

  return (
    <article className={`med-entry is-${entry.decision}`} aria-label={`${name}${strength ? ` ${strength}` : ""}`}>
      <header className="med-entry-head">
        <div>
          <h3>{name}{strength ? <span className="mg-num"> {strength}</span> : null}</h3>
          <p className="med-entry-sub">Medication {entry.index + 1}</p>
        </div>
        <span className={`status-chip med-decision is-${entry.decision}`}>
          {entry.decision === "confirmed" ? "Confirmed" : entry.decision === "rejected" ? "Rejected" : "Not reviewed"}
        </span>
      </header>

      {entry.review_notes.length > 0 && !decided && (
        <ul className="med-notes">
          {entry.review_notes.map((note) => <li key={note}>{NOTE_TEXT[note] || note}</li>)}
        </ul>
      )}

      {entry.matches.length > 0 && !decided && (
        <MatchPanel
          matches={entry.matches}
          acknowledged={acknowledged}
          disabled={busy}
          onToggle={(id) => {
            const next = new Set(acknowledged);
            if (next.has(id)) next.delete(id); else next.add(id);
            setAcknowledged(next);
          }}
        />
      )}

      <dl className="med-fields">
        {ordered.map((field) => {
          const value = currentValue(field);
          const changed = field.extracted != null && value !== field.extracted && (field.user_edited || editing);
          return (
            <div key={field.key} className={`med-field${field.key === "directions" ? " is-wide" : ""}`}>
              <dt>
                {field.label}
                {field.confidence !== "clearly_visible" && field.confidence !== "not_found" && (
                  <span className={`confidence-pill confidence-${field.confidence}`}>{CONFIDENCE_TEXT[field.confidence]}</span>
                )}
              </dt>
              <dd>
                {editing ? (
                  field.key === "directions" ? (
                    <textarea aria-label={field.label} rows={2} value={value} onChange={(event) => setDraft({ ...draft, [field.key]: event.target.value })} />
                  ) : (
                    <input aria-label={field.label} value={value} onChange={(event) => setDraft({ ...draft, [field.key]: event.target.value })} />
                  )
                ) : (
                  <span className={value ? "med-value" : "med-value is-empty"}>{value || "Not on the label"}</span>
                )}
                {(field.flags || []).filter((flag) => FLAG_TEXT[flag]).map((flag) => (
                  <small key={flag} className={`med-flag is-${flag}`}>{FLAG_TEXT[flag]}</small>
                ))}
                {changed && <small className="med-original">Read on the label as: {field.extracted || "nothing"}</small>}
              </dd>
            </div>
          );
        })}
      </dl>

      {entry.decision === "unverified" && (
        <div className="med-entry-actions">
          <label className="confirm">
            <input type="checkbox" checked={checked} onChange={(event) => setChecked(event.target.checked)} />
            I checked the name, strength and directions against the label.
          </label>
          <div className="med-entry-buttons">
            <button
              type="button"
              className="forest-button"
              disabled={busy || !checked || !allAcknowledged || nameMissing}
              title={nameMissing ? "Enter the medication name first" : !allAcknowledged ? "Compare with the existing record first" : undefined}
              onClick={() => void confirm()}
            >
              <Check size={15} /> {editing ? "Save correction and confirm" : "Confirm"}
            </button>
            {editing ? (
              <button type="button" className="quiet-button" onClick={() => { setEditing(false); setDraft({}); }}>Cancel edit</button>
            ) : (
              <button type="button" className="quiet-button" disabled={busy} onClick={() => setEditing(true)}><Pencil size={14} /> Edit</button>
            )}
            <button type="button" className="quiet-button" disabled={busy} onClick={() => onReject(entry)}><X size={14} /> Reject</button>
          </div>
        </div>
      )}
      {entry.decision === "confirmed" && <p className="med-entry-done"><Check size={14} /> Saved to your medications.</p>}
      {entry.decision === "rejected" && (
        <div className="med-entry-buttons">
          <p className="med-entry-done is-rejected">Not added to your medications.</p>
          <button type="button" className="quiet-button" disabled={busy} onClick={() => onRestore(entry)}><RotateCcw size={14} /> Review again</button>
        </div>
      )}
    </article>
  );
}

/**
 * Review of a medication label, prescription or list: the original label
 * stays on screen, each medication found is confirmed, corrected or
 * rejected on its own, and nothing is added to the medication list without
 * that step. A medication matching an existing record has to be compared
 * with it first; nothing is merged and neither record is treated as current.
 */
export function MedicationReview({ apiUrl, medState, onStateChange }: {
  apiUrl: string;
  medState: MedState;
  onStateChange: (state: MedState) => void;
}) {
  const [busyEntry, setBusyEntry] = useState<string | null>(null);
  const [error, setError] = useState("");
  const entries = medState.entries || [];
  const reviewed = entries.filter((entry) => entry.decision !== "unverified").length;

  async function call(entry: MedEntry, action: "confirm" | "reject" | "restore", body?: unknown): Promise<boolean> {
    setBusyEntry(entry.entry_id);
    setError("");
    try {
      const response = await apiFetch(`${apiUrl}/api/medications/v2/${medState.medication_id}/entries/${entry.entry_id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) {
        const apiError = await parseApiError(response, "MediGuide couldn't save this decision.");
        throw new Error(apiError.message);
      }
      onStateChange(await response.json());
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "MediGuide couldn't save this decision.");
      return false;
    } finally {
      setBusyEntry(null);
    }
  }

  return (
    <div className="extraction-grid doc-review-grid med-review-grid">
      <div className="med-source">
        {medState.source === "upload" && medState.preview_url ? (
          <div className="document-preview doc-page-preview">
            <AuthImage src={`${apiUrl}${medState.preview_url}`} alt="Original label" />
            <small>The original label. Check each detail against it.</small>
          </div>
        ) : null}
        {medState.label_text ? (
          <details className="med-label-text" open={medState.source !== "upload"}>
            <summary><FileText size={14} /> {medState.source === "upload" ? "Label text as read" : "Label text as you typed it"}</summary>
            <pre>{medState.label_text}</pre>
          </details>
        ) : null}
        {READ_NOTES[medState.text_source || ""] && <p className="med-read-note">{READ_NOTES[medState.text_source || ""]}</p>}
      </div>

      <div className="med-entries">
        <p className="eyebrow">{entries.length === 1 ? "1 MEDICATION FOUND" : `${entries.length} MEDICATIONS FOUND`}</p>
        <p className="med-review-progress" role="status">{reviewed} of {entries.length} reviewed. Only medications you confirm are added to your list.</p>
        {error && <p className="med-error" role="alert">{error}</p>}
        {entries.map((entry) => (
          <EntryCard
            key={entry.entry_id}
            entry={entry}
            busy={busyEntry === entry.entry_id}
            onConfirm={(target, fields, acknowledged) => call(target, "confirm", { fields, reviewed: true, acknowledged_record_ids: acknowledged })}
            onReject={(target) => void call(target, "reject")}
            onRestore={(target) => void call(target, "restore")}
          />
        ))}
      </div>
    </div>
  );
}
