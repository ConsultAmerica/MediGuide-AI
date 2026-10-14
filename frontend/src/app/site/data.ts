/**
 * Synthetic demo data for the public site. Never real patient information.
 * Values match data/samples/sample-lab-report.pdf, which "Try it with
 * synthetic data" loads, so what the site shows is what the demo produces.
 */

export const A1C_POINTS = [
  { label: "Jan 15", value: 6.2 },
  { label: "Apr 12", value: 6.5 },
  { label: "Aug 12", value: 6.7 },
] as const;

/** Printed on the synthetic report as "<5.7". */
export const A1C_RANGE_HIGH = 5.7;

/** Page 3 of the synthetic report (collection date Aug 12, 2026). */
export const REPORT_DATE = "Aug 12, 2026";
export const REPORT_ROWS = [
  { test: "Hemoglobin A1C", value: "6.7", unit: "%", range: "<5.7", flag: "H" },
  { test: "Hemoglobin", value: "12.9", unit: "g/dL", range: "12.0–15.5", flag: "" },
  { test: "Glucose", value: "99", unit: "mg/dL", range: "70–99", flag: "" },
  { test: "WBC", value: "6.4", unit: "10³/µL", range: "4.0–11.0", flag: "" },
  { test: "Platelets", value: "242", unit: "10³/µL", range: "150–400", flag: "" },
] as const;

export const MRI_REPORT = {
  title: "MRI Right Knee without contrast",
  date: "Feb 3, 2026",
  exam: "MRI of the right knee without contrast.",
  findings:
    "Small joint effusion. Mild thinning of the medial femoral cartilage. The menisci and ligaments appear intact.",
  impression: "Small joint effusion. Mild medial compartment cartilage thinning.",
  findingsList: [
    { text: "Small joint effusion", section: "Impression", state: "Confirmed by you" },
    { text: "Mild medial compartment cartilage thinning", section: "Impression", state: "Confirmed by you" },
    { text: "Menisci and ligaments appear intact", section: "Findings", state: "Needs your review" },
  ],
} as const;
