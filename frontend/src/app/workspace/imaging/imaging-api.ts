import { fetchWithTimeout, parseApiError, VISION_PROCESS_TIMEOUT_MS } from "../../../lib/api-error";
import { browserOcrField } from "../../../lib/browser-ocr";
import type {
  CompareBucket,
  FindingExplanation,
  ImagingFinding,
  ImagingSample,
  ImagingStudy,
  Modality,
  ModalitySummary,
  ReportGap,
  ReportLineItem,
  ReportSection,
} from "./imaging-types";

/** DICOM is intercepted client-side (see ImagingLanding/ImagingReportPanel
 * upload handlers) before any request is made, so this code path exists
 * only as a defensive fallback if that check is ever bypassed. */
export const DICOM_NOT_SUPPORTED_MESSAGE =
  "DICOM viewing isn't available yet. MediGuide currently supports imaging reports while DICOM study viewing is being prepared.";

async function asJson<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (!response.ok) {
    const apiError = await parseApiError(response, fallbackMessage);
    if (apiError.code === "DICOM_NOT_YET_SUPPORTED") {
      throw new Error(DICOM_NOT_SUPPORTED_MESSAGE);
    }
    throw new Error(apiError.message);
  }
  return response.json() as Promise<T>;
}

export function fetchModalities(apiUrl: string): Promise<{ modalities: ModalitySummary[] }> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/modalities`).then((r) =>
    asJson(r, "Could not load imaging categories."),
  );
}

export function fetchStudies(
  apiUrl: string,
  params: { modality?: string; body_region?: string; date_from?: string; date_to?: string } = {},
): Promise<{ studies: ImagingStudy[] }> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value);
  }
  const qs = query.toString();
  return fetchWithTimeout(`${apiUrl}/api/imaging/studies${qs ? `?${qs}` : ""}`).then((r) =>
    asJson(r, "Could not load studies."),
  );
}

export function fetchStudy(apiUrl: string, studyId: string): Promise<ImagingStudy> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/studies/${studyId}`).then((r) =>
    asJson(r, "Could not load this study."),
  );
}

export function createStudy(
  apiUrl: string,
  input: {
    modality: Modality;
    body_region: string;
    study_date: string | null;
    institution: string;
    study_description?: string;
  },
): Promise<ImagingStudy> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/studies`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  }).then((r) => asJson(r, "Could not create this study."));
}

export function deleteStudy(apiUrl: string, studyId: string): Promise<void> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/studies/${studyId}`, { method: "DELETE" }).then((r) =>
    asJson(r, "Could not delete this study."),
  );
}

export function uploadReport(
  apiUrl: string,
  studyId: string,
  file: File,
): Promise<{ document_id: string; sections: Record<string, string> }> {
  const form = new FormData();
  form.append("file", file);
  return browserOcrField(file)
    .then((clientOcr) => {
      if (clientOcr) form.append("client_ocr", clientOcr);
      return fetchWithTimeout(
        `${apiUrl}/api/imaging/studies/${studyId}/report`,
        { method: "POST", body: form },
        VISION_PROCESS_TIMEOUT_MS,
      );
    })
    .then((r) => asJson(r, "MediGuide could not read this imaging report."));
}

export interface ReportProcessingStatus {
  document_id?: string;
  status: string;
  stage: string;
  retry_attempt: number;
  retry_max: number;
  safe_error_message: string;
}

/** Polling target for a report upload in flight — keyed by study_id, not
 * document_id, since uploadReport() only learns the document_id once it
 * resolves (see ImagingStudy.pending_report_document_id's backend
 * docstring for why). Best-effort: swallow failures so a flaky poll tick
 * never surfaces as a user-facing error on top of whatever uploadReport()
 * itself reports. */
export async function fetchReportStatus(apiUrl: string, studyId: string): Promise<ReportProcessingStatus | null> {
  try {
    const response = await fetchWithTimeout(`${apiUrl}/api/imaging/studies/${studyId}/report/status`);
    if (!response.ok) return null;
    return (await response.json()) as ReportProcessingStatus;
  } catch {
    return null;
  }
}

export function fetchSections(apiUrl: string, studyId: string): Promise<{ sections: ReportSection[] }> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/studies/${studyId}/report/sections`).then((r) =>
    asJson(r, "Could not load report sections."),
  );
}

export function confirmSections(
  apiUrl: string,
  studyId: string,
  edits: { section_type: string; text: string }[],
  confirmTypes: string[],
): Promise<{ sections: ReportSection[]; verification_status: string }> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/studies/${studyId}/report/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewed: true, sections: edits, confirm_types: confirmTypes }),
  }).then((r) => asJson(r, "Could not confirm this report."));
}

type SectionsResult = { sections: ReportSection[]; verification_status: ImagingStudy["verification_status"] };

/** Confirm (optionally with a correction), reject or undo one section. Saved at once. */
export function decideSection(
  apiUrl: string,
  studyId: string,
  sectionType: string,
  decision: "confirmed" | "rejected" | "unverified",
  text?: string,
): Promise<SectionsResult> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/studies/${studyId}/report/sections/${encodeURIComponent(sectionType)}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(text === undefined ? { decision } : { decision, text }),
  }).then((r) => asJson(r, "Could not save this decision."));
}

export function fetchReportLines(apiUrl: string, studyId: string): Promise<{ lines: ReportLineItem[]; adjustable: boolean }> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/studies/${studyId}/report/lines`).then((r) =>
    asJson(r, "Could not load the report lines."),
  );
}

export function adjustBoundaries(
  apiUrl: string,
  studyId: string,
  sections: { section_type: string; line_start: number; line_end: number }[],
): Promise<SectionsResult> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/studies/${studyId}/report/sections/boundaries`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sections }),
  }).then((r) => asJson(r, "Could not change the section boundaries."));
}

export function applyReportDetails(apiUrl: string, studyId: string, fields: string[]): Promise<ImagingStudy> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/studies/${studyId}/report/details/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields }),
  }).then((r) => asJson(r, "Could not update the study details."));
}

export function compareReports(
  apiUrl: string,
  documentIdA: string,
  documentIdB: string,
): Promise<{ comparisons: CompareBucket[] }> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id_a: documentIdA, document_id_b: documentIdB }),
  }).then((r) => asJson(r, "Could not compare these reports."));
}

export function explainTerm(
  apiUrl: string,
  term: string,
  modality?: string,
): Promise<{ term: string; answer_markdown: string; sources: { title: string; publisher: string }[] }> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/terminology/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ term, modality }),
  }).then((r) => asJson(r, "Could not explain this term right now."));
}

export function fetchImagingSamples(apiUrl: string): Promise<{ samples: ImagingSample[] }> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/samples`).then((r) =>
    asJson(r, "Could not load sample imaging reports."),
  );
}

export async function downloadImagingSample(apiUrl: string, slug: string, filename: string): Promise<File> {
  const response = await fetchWithTimeout(`${apiUrl}/api/imaging/samples/${encodeURIComponent(slug)}`);
  if (!response.ok) {
    const apiError = await parseApiError(response, "Could not download this sample report.");
    throw new Error(apiError.message);
  }
  const blob = await response.blob();
  return new File([blob], filename || `${slug}.pdf`, { type: "application/pdf" });
}

export function reportPagePreviewUrl(apiUrl: string, studyId: string, page: number): string {
  return `${apiUrl}/api/imaging/studies/${studyId}/report/pages/${page}/preview`;
}

export function fetchFindings(
  apiUrl: string,
  studyId: string,
): Promise<{ findings: ImagingFinding[]; gaps: ReportGap[]; boundary: string }> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/studies/${studyId}/findings`).then((r) =>
    asJson(r, "Could not load report findings."),
  );
}

export function confirmFindings(
  apiUrl: string,
  studyId: string,
  findings: { finding_id: string; confirmed_text?: string; verification_status: string }[],
): Promise<{ findings: ImagingFinding[] }> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/studies/${studyId}/findings/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewed: true, findings }),
  }).then((r) => asJson(r, "Could not confirm these findings."));
}

export function explainFinding(apiUrl: string, findingId: string): Promise<FindingExplanation> {
  return fetchWithTimeout(`${apiUrl}/api/imaging/findings/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ finding_id: findingId }),
  }).then((r) => asJson(r, "Educational explanation is temporarily unavailable."));
}
