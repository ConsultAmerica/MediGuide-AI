// Shared types, constants, and pure helpers used by both WorkspaceStateProvider
// and the view components rendered from WorkspaceApp.tsx. Moved verbatim out of
// WorkspaceApp.tsx so both sides of the state/view split can import them.

import { BookOpen, FileText, Stethoscope } from "lucide-react";
import { API_BASE_URL } from "../../../lib/auth";

export type Source = { number: number; title: string; publisher: string; published?: string; reviewed?: string; url?: string; passage?: string };
export type LibrarySource = { id: string; title: string; publisher: string; url?: string; published?: string; reviewed?: string; type?: string };
export type Message = { role: "user" | "assistant"; content: string };
export type DocFieldStatus = "in_listed_range" | "outside_listed_range" | "flagged_high_on_report" | "flagged_low_on_report" | "not_applicable" | "unknown";
export type DocFieldConfidence = "clearly_visible" | "needs_review" | "could_not_read";
export const DOC_STATUS_LABELS: Record<DocFieldStatus, string> = {
  in_listed_range: "",
  outside_listed_range: "",
  flagged_high_on_report: "Flagged high on this report",
  flagged_low_on_report: "Flagged low on this report",
  not_applicable: "",
  unknown: "",
};
export const DOC_CONFIDENCE_LABELS: Record<DocFieldConfidence, string> = { clearly_visible: "Clearly visible", needs_review: "Needs review", could_not_read: "Could not read" };
export type DocField = {
  field_id: string; label: string; value: string; unit: string; reference_range: string;
  status: DocFieldStatus; confidence: DocFieldConfidence; page_number: number; source_text: string;
  extraction_method?: string; user_edited: boolean;
  /** Extraction v2 provenance: flag as printed, source region (PDF points), original extraction. */
  flag?: string; source_bbox?: number[] | null; extracted?: { label: string; value: string; unit: string; reference_range: string } | null;
};
export type DocPage = {
  page_number: number; preview_url: string; text_available: boolean; extracted_field_count: number;
  width?: number; height?: number;
  /** How the page was read and how readable it was (not a measure of medical accuracy). */
  text_source?: "text_layer" | "ocr" | "vision" | "none" | ""; quality?: "good" | "fair" | "poor" | "unreadable" | "";
  quality_notes?: string[]; ocr_confidence?: number | null;
};
/** Lowest extraction version whose lab field mapping is trustworthy (v2: position-based
 * table reading). Unconfirmed documents read before it are offered a re-read. */
export const CURRENT_EXTRACTION_VERSION = 2;
export type DocState = {
  document_id: string; filename: string; page_count: number; status: string; pages: DocPage[]; fields: DocField[]; confirmed: boolean;
  content_type?: string; extraction_version?: number; content_sha256?: string; duplicate_of?: { document_id: string; filename: string } | null;
  /** A partially completed review saved on the server (decisions and edits only, not a record). */
  review_draft?: Record<string, ReviewDraftItem>; review_draft_saved_at?: string;
};
export type FieldReviewDecision = "unverified" | "confirmed" | "corrected" | "rejected";
export type ReviewDraftItem = { state: FieldReviewDecision; label?: string | null; value?: string | null; unit?: string | null; reference_range?: string | null };
export type DraftSaveStatus = "idle" | "saving" | "saved" | "error";
export const REVIEWABLE_KEYS = ["label", "value", "unit", "reference_range"] as const;
export type ReviewablePatch = Partial<Pick<DocField, (typeof REVIEWABLE_KEYS)[number]>>;

/** Lays a saved review draft over the extraction: the reviewer's edits on the
 * fields, and their decision per field (unverified when there is none). */
export function applyReviewDraft(state: DocState): { fields: DocField[]; review: Record<string, FieldReviewDecision> } {
  const draft = state.review_draft || {};
  const review: Record<string, FieldReviewDecision> = {};
  const fields = (state.fields || []).map((field) => {
    const item = draft[field.field_id];
    review[field.field_id] = item?.state || "unverified";
    if (!item) return field;
    const patch: ReviewablePatch = {};
    for (const key of REVIEWABLE_KEYS) {
      const value = item[key];
      if (typeof value === "string" && value !== field[key]) patch[key] = value;
    }
    return Object.keys(patch).length ? { ...field, ...patch, user_edited: true } : field;
  });
  return { fields, review };
}

/** The draft to save: every decided or edited field, with only the edited values. */
export function buildReviewDraft(fields: DocField[], original: DocField[], review: Record<string, FieldReviewDecision>): Record<string, ReviewDraftItem> {
  const byId = new Map(original.map((field) => [field.field_id, field]));
  const items: Record<string, ReviewDraftItem> = {};
  for (const field of fields) {
    const base = byId.get(field.field_id);
    if (!base) continue;
    const item: ReviewDraftItem = { state: review[field.field_id] || "unverified" };
    let edited = false;
    for (const key of REVIEWABLE_KEYS) {
      if (field[key] !== base[key]) { item[key] = field[key]; edited = true; }
    }
    if (edited || item.state !== "unverified") items[field.field_id] = item;
  }
  return items;
}

/** Values a reviewer can confirm in one step: read from a real text layer,
 * clearly visible, with a recorded source region and a value present. */
export function isBulkConfirmable(field: DocField): boolean {
  return field.extraction_method === "native_text"
    && field.confidence === "clearly_visible"
    && Array.isArray(field.source_bbox) && field.source_bbox.length === 4
    && field.value.trim() !== "";
}
export type DocSession = { document_id: string; filename: string; status: string; page_count: number; field_count: number; confirmed: boolean };
export type DocUploadResult = { document_id: string; filename: string; content_type?: string; file_size?: number; status: string };
export type DocEvidenceSource = { citation_number: number; title: string; publisher: string; source_url?: string; passage?: string };
export type DocExplain = { document_id: string; answer_markdown: string; document_pages_cited: number[]; sources: DocEvidenceSource[]; limitations: string[] };
export type HealthStatus = { status: string; detail: string };
export type HealthResponse = { status: string; ready: number; total: number; statuses: Record<string, HealthStatus>; ai_available?: boolean; server_ocr?: boolean; answer_mode?: "ai" | "sources" | "off"; knowledge?: { active_chunks?: number; approved_sources?: number } };
export type MedField = {
  key: string; label: string; value: string; confidence: DocFieldConfidence | "not_found"; source_text: string; user_edited: boolean;
  /** e.g. from_directions, ambiguous_directions, dose_range, shared_detail, ai_read */
  flags?: string[];
  /** What was read before review. */
  extracted?: string | null;
  page?: number;
};
export type MedMatch = {
  record_id: string; kind: "possible_duplicate" | "conflict"; medication_name: string; strength: string; directions: string;
  source: string; confirmed_at: string | null;
  differences: { field: string; label: string; this_label: string; existing_record: string }[];
};
export type MedEntry = {
  entry_id: string; index: number; fields: MedField[]; review_notes: string[];
  decision: "unverified" | "confirmed" | "rejected"; record_id: string | null; matches: MedMatch[];
};
export type MedState = {
  medication_id: string; source: "upload" | "typed"; filename: string; preview_url: string; status: string; fields: MedField[];
  other_visible_text: string; confirmed: boolean;
  entries?: MedEntry[];
  /** The label text exactly as read, and how: typed | text_layer | ocr | vision | typed_ai */
  label_text?: string; text_source?: string;
};
export type MedRecord = {
  medication_id: string; medication_name: string; brand_name: string; generic_name: string; strength: string; dosage_form: string;
  route: string; dose: string; frequency: string; directions: string; quantity: string; refills: string; prescriber: string;
  pharmacy: string; prescription_date: string; source: string; filename: string; text_source: string; confirmed_at: string | null;
  review_flags: string[]; extracted: Record<string, string> | null; matches: MedMatch[];
};
export type MedInfo = { medication_id: string; answer_markdown: string; sources: DocEvidenceSource[]; limitations: string[] };
export type LabTest = { test_code: string; display_name: string; observation_count: number; has_data: boolean };
export type LabPoint = {
  observation_id: string;
  test_code: string;
  test_name: string;
  normalized_name?: string;
  /** The test name exactly as printed and confirmed. */
  original_name?: string;
  /** Plottable number; null for "<0.5", "Positive" and other non-plain values. */
  value: number | null;
  value_text: string;
  value_qualifier?: string;
  /** What extraction read before review, and what the reviewer kept (as text). */
  extracted_value?: string | null;
  confirmed_value?: string | null;
  review_status?: string;
  reviewed_at?: string | null;
  unit: string;
  unit_key?: string;
  /** The date the result is filed under, and which kind of date it is. */
  date?: string | null;
  date_source?: "collection" | "report" | "unknown" | "";
  report_date: string | null;
  collection_date?: string | null;
  source_text?: string;
  source_bbox?: number[] | null;
  /** Whether the chart draws this result, and why not when it doesn't. */
  plotted?: boolean;
  not_plotted_reason?: "duplicate" | "qualified_value" | "not_numeric" | "no_date" | "different_unit" | null;
  duplicate_of?: string | null;
  duplicate_document_name?: string | null;
  conflicting_values?: string[];
  document_id: string;
  document_name: string;
  page_number: number;
  source_page?: number;
  field_id: string;
  verification_state: string;
  verification_status?: string;
  confidence?: string;
  extraction_method?: string;
  range_status?: string;
  source_flag?: string;
  reference_text?: string;
  reference_range?: string;
  /** Parsed from the printed range when it is numeric (null otherwise). */
  reference_low?: number | null;
  reference_high?: number | null;
  change_from_previous?: number | null;
  change_direction?: "up" | "down" | "unchanged" | null;
};
export type SystemComponent = { name: string; key: string; status: string; detail: string };
export type SystemStatus = { service: string; overall: string; components: SystemComponent[]; knowledge: { active_chunks?: number; approved_sources?: number } };
export type View = "conversation" | "timeline" | "documents" | "labs" | "imaging" | "medication" | "visit" | "sources" | "system" | "evaluation" | "demo";

// Maps the pre-routing `View` union onto real `/workspace/<segment>` routes.
// Kept alongside `View` so the redirect shim (old `?view=` links) and the
// state provider (new `router.push` navigation) share one mapping.
export const VIEW_TO_PATH: Record<View, string> = {
  conversation: "ask",
  timeline: "timeline",
  documents: "documents",
  labs: "labs",
  imaging: "imaging",
  medication: "medications",
  visit: "visit",
  sources: "sources",
  system: "system",
  evaluation: "evaluation",
  demo: "demo",
};

const PATH_TO_VIEW: Record<string, View> = Object.fromEntries(
  Object.entries(VIEW_TO_PATH).map(([view, path]) => [path, view as View]),
) as Record<string, View>;

// Only "documents" and "medication" are ever actually branched on (Evidence
// panel context) — an unmatched segment (e.g. "home") legitimately returns
// undefined and falls through to the generic branches.
export function pathToView(pathname: string): View | undefined {
  const segment = pathname.replace(/^\/workspace\/?/, "").split("/")[0];
  return PATH_TO_VIEW[segment];
}
export type AnswerStatus = "answered" | "sources_only" | "withheld" | "emergency" | "no_evidence" | "error" | "";
export type SseEvent =
  | { type: "stage"; stage: string }
  | { type: "sources"; sources: Source[] }
  | { type: "delta"; text: string }
  | { type: "done"; answer: string; sources: Source[]; status: AnswerStatus };

export async function* readSseEvents(response: Response): AsyncGenerator<SseEvent> {
  const reader = response.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.split("\n").find((part) => part.startsWith("data: "));
      if (!line) continue;
      const payload = line.slice(6);
      if (payload === "[DONE]") return;
      try { yield JSON.parse(payload) as SseEvent; } catch { /* ignore malformed frame */ }
    }
  }
}

export const API_URL = API_BASE_URL;
export const API_CONFIGURATION_MESSAGE = "The deployed frontend has no AI service URL. Set NEXT_PUBLIC_API_URL to the HTTPS address of the FastAPI backend and redeploy.";
export const quickActions = [
  ["Blood pressure", "Systolic, diastolic, and why it matters.", BookOpen, "What is blood pressure?"],
  ["Lab results", "Understand hemoglobin and CBC basics.", FileText, "What is hemoglobin in a CBC lab test?"],
  ["Medication labels", "Review antibiotic and label basics.", Stethoscope, "What should I understand about amoxicillin and medication labels?"],
] as const;

export const topicSuggestions = [
  ["Blood pressure", "What is blood pressure?"],
  ["Lab results", "What is hemoglobin in a CBC lab test?"],
  ["Medication labels", "What should I understand about medication labels?"],
  ["Prepare for a visit", "How should I prepare for a healthcare appointment?"],
] as const;

export const healthLabels: Record<string, string> = {
  fastapi: "MediGuide API",
  ollama: "Educational explanations",
  text_model: "Educational explanations",
  vision_model: "Document reading",
  embedding_model: "Educational sources",
  vector_store: "Educational sources",
  database: "Document storage",
  whisper: "Voice transcription",
  piper: "Voice playback",
  translation_model: "Translation",
};

export function suggestClinicianQuestions(fields: DocField[], medFields: MedField[], labPoints: LabPoint[]) {
  const questions: string[] = [];
  for (const field of fields.filter((item) => item.label.toLowerCase() !== "report date" && item.value).slice(0, 4)) {
    questions.push(`Has my ${field.label} (${field.value}${field.unit ? ` ${field.unit}` : ""}) changed compared with previous results?`);
    if (field.reference_range) {
      questions.push(`The report lists ${field.reference_range} for ${field.label}. Should this be repeated or discussed?`);
    }
  }
  if (labPoints.length) questions.push("Are there trends over time I should ask about?");
  const medName = medFields.find((field) => field.key === "medication_name" || field.key === "name")?.value;
  if (medName) questions.push(`Could ${medName} affect these lab values?`);
  if (!questions.length) {
    return "What do these results mean for me?\nShould any tests be repeated?\nWhat should I watch for before the next visit?";
  }
  return [...new Set(questions)].slice(0, 6).join("\n");
}

export function downloadTextFile(filename: string, contents: string) {
  const blob = new Blob([contents], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function downloadCsv(filename: string, rows: string[][]) {
  const csv = rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, "\"\"")}"`).join(",")).join("\n");
  downloadTextFile(filename, csv);
}

export const SETTINGS_STORAGE_KEY = "mediguide.workspace-settings";
export const VISIT_STORAGE_KEY = "mediguide.visit-draft";

export function readStoredSettings() {
  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    return raw ? JSON.parse(raw) as { answerDetail?: "Concise" | "Standard" | "Detailed"; readingLevel?: "Standard" | "Plain"; language?: string } : {};
  } catch {
    return {};
  }
}
