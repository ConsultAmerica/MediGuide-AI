export type Modality = "xray" | "ct" | "mri" | "ultrasound" | "pet_ct";

export const MODALITY_ORDER: Modality[] = ["xray", "ct", "mri", "ultrasound", "pet_ct"];

export const MODALITY_LABELS: Record<Modality, string> = {
  xray: "X-Ray",
  ct: "CT",
  mri: "MRI",
  ultrasound: "Ultrasound",
  pet_ct: "PET/CT",
};

export const SECTION_LABELS: Record<string, string> = {
  exam: "Exam",
  clinical_history: "Clinical History",
  technique: "Technique",
  comparison: "Comparison",
  findings: "Findings",
  impression: "Impression",
  recommendations: "Recommendations",
};

export const SECTION_ORDER = Object.keys(SECTION_LABELS);

export interface ImagingSample {
  slug: string;
  modality: Modality;
  modality_label: string;
  body_region: string;
  title: string;
  filename: string;
}

export interface ModalitySummary {
  modality: Modality;
  label: string;
  study_count: number;
  latest_study_date: string | null;
}

export interface ImagingStudy {
  study_id: string;
  modality: Modality;
  body_region: string;
  study_description: string;
  study_date: string | null;
  institution: string;
  report_document_id: string | null;
  report_page_count?: number | null;
  /** What the report itself says about the study, and what the user applied. */
  report_details?: ReportDetails | null;
  verification_status: "unverified" | "partially_verified" | "verified";
  created_at: string;
}

export interface ReportDetail {
  value: string;
  as_printed: string;
  page: number;
}

export interface ReportDetails {
  classification?: {
    category: "radiology_report" | "not_radiology_report" | "uncertain";
    modality: string | null;
    modality_label: string;
    modality_evidence: string;
    headers_found: string[];
  };
  details?: Partial<Record<"exam_date" | "ordering_clinician" | "facility" | "study_description" | "body_region", ReportDetail>>;
  applied?: Record<string, { value: string | null; previous: string | null; applied_at: string }>;
}

export interface SourceRegion {
  page: number;
  bbox: [number, number, number, number];
  width: number;
  height: number;
}

export interface ReportLineItem {
  index: number;
  page: number;
  text: string;
}

export interface ReportSection {
  section_id: string;
  study_id: string;
  document_id: string;
  section_type: string;
  section_text: string;
  original_text: string;
  page_number: number;
  page_end?: number;
  source_text: string;
  verification_status: "unverified" | "confirmed" | "rejected";
  /** native_text | tesseract_ocr | vision_ocr */
  extraction_method?: string;
  source_regions?: SourceRegion[];
  line_start?: number | null;
  line_end?: number | null;
  boundary_adjusted?: boolean;
  reviewed_at?: string | null;
}

export interface CompareSide {
  text: string;
  document_id: string;
  page_number: number | null;
}

export interface CompareBucket {
  section_type: string;
  earlier: CompareSide;
  later: CompareSide;
  present_in_both: string[];
  newly_mentioned: string[];
  no_longer_mentioned: string[];
}

export interface TermExplanation {
  text: string;
  sourceExcerpt: string;
  sources: { title: string; publisher: string }[];
}

export interface ImagingFinding {
  finding_id: string;
  study_id: string;
  report_section_id: string | null;
  section: string;
  ordinal: number;
  finding_text: string;
  original_text: string;
  confirmed_text: string;
  normalized_concept: string;
  anatomy: string;
  laterality: string;
  source_document_id: string;
  source_page: number;
  summary_label: string;
  verification_status: "unverified" | "confirmed" | "rejected" | "could_not_read";
  bbox: { x: number; y: number; width: number; height: number } | null;
}

export interface ReportGap {
  label: string;
  note: string;
}

export interface FindingExplanation {
  finding: ImagingFinding;
  record_provenance: {
    finding_id: string;
    finding_text: string;
    section: string;
    source_document_id: string;
    source_page: number;
    verification_status: string;
  };
  answer_markdown: string;
  sources: { citation_number: number; title: string; publisher: string; source_url?: string; passage?: string }[];
  education_available: boolean;
  unavailable_reason: string;
  education_provenance?: { citations: unknown[]; corpus: string };
}

export type ImagingView = "landing" | "list" | "detail" | "history" | "compare";

/**
 * Every input here is real, already-persisted backend state (the study's
 * report_document_id + its sections' verification_status) — the only
 * exception is `transientStatus`, which reflects an upload request actually
 * in flight (or having just failed) in *this* browser session. There is no
 * backend "processing"/"failed" column to read instead: the upload
 * endpoint is a single combined call with no separate status-polling
 * endpoint, so those two states can only ever be client-visible request
 * state, never fabricated persisted state.
 */
export type ReportState =
  | "no_report"
  | "processing"
  | "review_required"
  | "partially_verified"
  | "verified"
  | "failed";

export function deriveReportState(
  study: ImagingStudy,
  sections: ReportSection[],
  transientStatus: "processing" | "failed" | null,
): ReportState {
  if (transientStatus) return transientStatus;
  if (!study.report_document_id) return "no_report";
  // study.verification_status is itself derived server-side from the
  // sections' own verification_status (see derive_study_verification_status
  // in src/database/imaging_repository.py), so it alone is authoritative —
  // callers that haven't fetched sections (list/history views) still get an
  // accurate state instead of defaulting to "review required".
  if (study.verification_status === "verified") return "verified";
  if (study.verification_status === "partially_verified") return "partially_verified";
  if (sections.length === 0) return "review_required";
  const confirmedCount = sections.filter((s) => s.verification_status === "confirmed").length;
  return confirmedCount > 0 ? "partially_verified" : "review_required";
}

export const REPORT_STATE_LABELS: Record<ReportState, string> = {
  no_report: "No report",
  processing: "Processing",
  review_required: "Review required",
  partially_verified: "Partially verified",
  verified: "Verified",
  failed: "Processing failed",
};

export function formatStudyDate(value: string | null): string {
  if (!value) return "Undated";
  try {
    return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
    });
  } catch {
    return value;
  }
}
