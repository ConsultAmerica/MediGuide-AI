"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Pill } from "lucide-react";
import { apiFetch } from "../../../lib/auth";
import type { MedRecord } from "../_state/workspace-shared";

function addedOn(value: string | null) {
  return value ? new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";
}

/**
 * The medications the user has confirmed, each with where it came from.
 * When two records name the same medication with different details, both
 * are shown with the difference; MediGuide never picks one as current.
 */
export function MedicationRecords({ apiUrl, refreshKey }: { apiUrl: string; refreshKey: string }) {
  const [records, setRecords] = useState<MedRecord[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch(`${apiUrl}/api/medications/v2/records`)
      .then((response) => (response.ok ? response.json() : { records: [] }))
      .then((data: { records: MedRecord[] }) => { if (!cancelled) setRecords(data.records || []); })
      .catch(() => { if (!cancelled) setRecords([]); });
    return () => { cancelled = true; };
  }, [apiUrl, refreshKey]);

  if (!records?.length) return null;
  const byId = new Map(records.map((record) => [record.medication_id, record]));

  return (
    <section className="med-records" aria-labelledby="med-records-title">
      <p className="eyebrow" id="med-records-title">YOUR CONFIRMED MEDICATIONS</p>
      <p className="med-records-help">Only medications you confirmed are listed. Each keeps the label it came from.</p>
      <ul>
        {records.map((record) => {
          const conflicts = record.matches.filter((match) => match.kind === "conflict");
          const duplicates = record.matches.filter((match) => match.kind === "possible_duplicate");
          return (
            <li key={record.medication_id} className={conflicts.length ? "has-conflict" : ""}>
              <Pill size={16} aria-hidden="true" />
              <div>
                <strong>{record.medication_name}{record.strength ? ` ${record.strength}` : ""}{record.dosage_form ? ` ${record.dosage_form}` : ""}</strong>
                <p>{record.directions || "No directions on the label"}</p>
                <small>
                  From {record.filename || (record.source === "typed" ? "a typed label" : "an uploaded label")}
                  {record.confirmed_at ? ` · added ${addedOn(record.confirmed_at)}` : ""}
                </small>
                {conflicts.map((match) => (
                  <p key={match.record_id} className="med-record-conflict">
                    <AlertTriangle size={13} aria-hidden="true" /> Another {match.medication_name} record
                    {byId.get(match.record_id)?.filename ? ` (from ${byId.get(match.record_id)?.filename})` : ""} has different{" "}
                    {match.differences.map((difference) => difference.label.toLowerCase()).join(", ")}. Both are kept; check with your pharmacist which applies.
                  </p>
                ))}
                {duplicates.length > 0 && !conflicts.length && (
                  <p className="med-record-duplicate">Possibly listed twice: another record has the same details.</p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
