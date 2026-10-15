import { Check } from "lucide-react";
import { REPORT_STATE_LABELS, type ReportState } from "./imaging-types";

const CHIP_CLASS: Record<ReportState, string> = {
  no_report: "status-dot idle",
  processing: "status-dot busy",
  review_required: "status-dot limited",
  partially_verified: "status-dot limited",
  verified: "status-dot",
  failed: "status-dot off",
};

/** Status text is never conveyed by color alone — the label always renders
 * alongside the dot, so the state is legible without color perception. */
export function ImagingStatusChip({ state }: { state: ReportState }) {
  if (state === "verified") {
    return (
      <span className="lab-verified">
        <Check size={13} /> {REPORT_STATE_LABELS[state]}
      </span>
    );
  }
  return (
    <span className="imaging-status-chip">
      <span className={CHIP_CLASS[state]} />
      {REPORT_STATE_LABELS[state]}
    </span>
  );
}
