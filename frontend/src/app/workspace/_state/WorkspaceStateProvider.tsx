"use client";

// All cross-view state and handlers that used to live directly in
// WorkspaceApp.tsx (lines 173-1029 of the pre-split file), moved verbatim
// into a context so it survives Next.js route changes the same way it
// survived `view` state changes before real routing existed. See
// C:\Users\nazia\.claude\plans\idempotent-riding-bentley.md for why this is
// one shared context rather than split per view for Phase 1.

import {
  ChangeEvent,
  DragEvent,
  FormEvent,
  KeyboardEvent,
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { DEMO_MEDICATION_LABEL_TEXT } from "../../../lib/demo-data";
import { fetchWithTimeout, parseApiError, VISION_PROCESS_TIMEOUT_MS } from "../../../lib/api-error";
import { mapStatusToProcessStage, type ProcessStageId, type ToastItem } from "../polish-ui";
import {
  API_CONFIGURATION_MESSAGE,
  API_URL,
  pathToView,
  readSseEvents,
  readStoredSettings,
  REVIEWABLE_KEYS,
  applyReviewDraft,
  buildReviewDraft,
  SETTINGS_STORAGE_KEY,
  suggestClinicianQuestions,
  VISIT_STORAGE_KEY,
  VIEW_TO_PATH,
  downloadCsv,
  type AnswerStatus,
  type DocExplain,
  type DocField,
  type DocSession,
  type DocState,
  type DocUploadResult,
  type DraftSaveStatus,
  type FieldReviewDecision,
  type ReviewablePatch,
  type HealthResponse,
  type LabPoint,
  type LabTest,
  type MedField,
  type MedInfo,
  type MedState,
  type Message,
  type Source,
  type SystemStatus,
  type View,
} from "./workspace-shared";
import { apiFetch } from "../../../lib/auth";

function useWorkspaceState() {
  const router = useRouter();
  const pathname = usePathname();
  const view = pathToView(pathname);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [answer, setAnswer] = useState("");
  const [answerStatus, setAnswerStatus] = useState<AnswerStatus>("");
  const [streaming, setStreaming] = useState(false);
  const [question, setQuestion] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [loadingStage, setLoadingStage] = useState("");
  const [error, setError] = useState("");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthOpen, setHealthOpen] = useState(false);
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [pendingTranscript, setPendingTranscript] = useState("");
  const [transcriptReviewed, setTranscriptReviewed] = useState(false);
  const [selectedSource, setSelectedSource] = useState<number | null>(null);
  const [language, setLanguage] = useState("English");
  const [recording, setRecording] = useState(false);
  const [docState, setDocState] = useState<DocState | null>(null);
  const [docFields, setDocFields] = useState<DocField[]>([]);
  const [docConfirmed, setDocConfirmed] = useState(false);
  const [docReviewChecked, setDocReviewChecked] = useState(false);
  const [docSelectedPage, setDocSelectedPage] = useState(1);
  const [docExplain, setDocExplain] = useState<DocExplain | null>(null);
  const [docQuestion, setDocQuestion] = useState("");
  const [documentDragging, setDocumentDragging] = useState(false);
  const [medState, setMedState] = useState<MedState | null>(null);
  const [medFields, setMedFields] = useState<MedField[]>([]);
  const [medConfirmed, setMedConfirmed] = useState(false);
  const [medReviewChecked, setMedReviewChecked] = useState(false);
  const [medInfo, setMedInfo] = useState<MedInfo | null>(null);
  const [medQuestion, setMedQuestion] = useState("");
  const [medTypedText, setMedTypedText] = useState("");
  const [medDragging, setMedDragging] = useState(false);
  const [visitFields, setVisitFields] = useState<Record<string, string>>({});
  const [visitStep, setVisitStep] = useState(1);
  const [addConfirmedLabsHint, setAddConfirmedLabsHint] = useState("");
  const [demoGuide, setDemoGuide] = useState("");
  const [confirmedLabCodes, setConfirmedLabCodes] = useState<string[]>([]);
  const [docErrorKind, setDocErrorKind] = useState<"upload" | "extract" | "confirm" | "explain" | "sample" | "">("");
  const [pendingDocId, setPendingDocId] = useState<string | null>(null);
  const [highlightedFieldId, setHighlightedFieldId] = useState<string | null>(null);
  const [processStage, setProcessStage] = useState<ProcessStageId | null>(null);
  const [processFailed, setProcessFailed] = useState(false);
  // Live automatic-retry progress, polled from /status alongside processStage
  // above (see processDocument()) — null unless the backend is currently
  // mid-retry against an unreachable/slow AI service.
  const [processRetry, setProcessRetry] = useState<{ attempt: number; max: number } | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [confirmDeleteObservationId, setConfirmDeleteObservationId] = useState<string | null>(null);
  const [confirmResetDocument, setConfirmResetDocument] = useState(false);
  const [sourceBreadcrumb, setSourceBreadcrumb] = useState("");
  const [previewZoom, setPreviewZoom] = useState(1);
  const [fieldReviewState, setFieldReviewState] = useState<Record<string, FieldReviewDecision>>({});
  // The extraction exactly as the server read it, so a correction can be
  // compared with (and undone back to) what was on the page.
  const [docOriginalFields, setDocOriginalFields] = useState<DocField[]>([]);
  const [draftStatus, setDraftStatus] = useState<DraftSaveStatus>("idle");
  const lastSavedDraft = useRef("");
  // Set while a confirmation is in flight: a draft save that fires then
  // would reach a document that is already confirmed (and be refused).
  const confirmingDocument = useRef(false);
  const [labTests, setLabTests] = useState<LabTest[]>([]);
  const [selectedLabCode, setSelectedLabCode] = useState("hemoglobin_a1c");
  const [labPoints, setLabPoints] = useState<LabPoint[]>([]);
  const [labSummary, setLabSummary] = useState<LabPoint[]>([]);
  const [recentSessions, setRecentSessions] = useState<DocSession[]>([]);
  const [selectedLabPoint, setSelectedLabPoint] = useState<LabPoint | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [answerDetail, setAnswerDetail] = useState<"Concise" | "Standard" | "Detailed">("Standard");
  const [readingLevel, setReadingLevel] = useState<"Standard" | "Plain">("Standard");
  const fileInput = useRef<HTMLInputElement>(null);
  const medFileInput = useRef<HTMLInputElement>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);

  function pushToast(message: string, tone: ToastItem["tone"] = "info") {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((current) => [...current.slice(-3), { id, message, tone }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== id));
    }, tone === "error" ? 8000 : 4200);
  }

  useEffect(() => { void checkHealth(); }, []);
  // Autosave the in-progress review (debounced) so it can be resumed later.
  const draftDocumentId = docState?.document_id;
  useEffect(() => {
    if (!draftDocumentId || docConfirmed || !docOriginalFields.length) return;
    const items = buildReviewDraft(docFields, docOriginalFields, fieldReviewState);
    const body = JSON.stringify(items);
    if (body === lastSavedDraft.current) return;
    const timer = window.setTimeout(async () => {
      if (confirmingDocument.current) return;
      setDraftStatus("saving");
      try {
        const response = await apiFetch(`${API_URL}/api/documents/v2/${draftDocumentId}/review-draft`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items }),
        });
        if (!response.ok) throw new Error("draft not saved");
        lastSavedDraft.current = body;
        setDraftStatus("saved");
      } catch {
        setDraftStatus("error");
      }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [draftDocumentId, docConfirmed, docFields, docOriginalFields, fieldReviewState]);
  useEffect(() => {
    // One-time hydration from localStorage/sessionStorage (external systems),
    // not a value derivable from props/state during render.
    /* eslint-disable react-hooks/set-state-in-effect */
    const stored = readStoredSettings();
    if (stored.answerDetail) setAnswerDetail(stored.answerDetail);
    if (stored.readingLevel) setReadingLevel(stored.readingLevel);
    if (stored.language) setLanguage(stored.language);
    try {
      const visitDraft = window.sessionStorage.getItem(VISIT_STORAGE_KEY);
      if (visitDraft) setVisitFields(JSON.parse(visitDraft) as Record<string, string>);
    } catch { /* ignore */ }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);
  useEffect(() => {
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify({ answerDetail, readingLevel, language }));
  }, [answerDetail, readingLevel, language]);
  useEffect(() => {
    window.sessionStorage.setItem(VISIT_STORAGE_KEY, JSON.stringify(visitFields));
  }, [visitFields]);
  useEffect(() => {
    if (!mobileNavOpen) return;
    const closeOnEscape = (event: globalThis.KeyboardEvent) => { if (event.key === "Escape") setMobileNavOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [mobileNavOpen]);

  async function checkHealth() {
    try { const response = await apiFetch(`${API_URL}/api/health`); if (!response.ok) throw new Error(); setHealth(await response.json()); }
    catch { setHealth({ status: "unavailable", ready: 0, total: 10, statuses: {} }); }
  }

  async function loadLabs(testCode: string) {
    try {
      const [testsRes, timelineRes] = await Promise.all([
        apiFetch(`${API_URL}/api/labs/tests`),
        apiFetch(`${API_URL}/api/labs/timeline/${encodeURIComponent(testCode)}`),
      ]);
      if (testsRes.ok) {
        const data = await testsRes.json();
        setLabTests(data.tests || []);
      }
      if (timelineRes.ok) {
        const data = await timelineRes.json();
        setLabPoints(data.points || []);
      } else {
        setLabPoints([]);
      }
    } catch {
      setLabTests([]);
      setLabPoints([]);
    }
  }

  async function loadLabSummary() {
    try {
      const response = await apiFetch(`${API_URL}/api/labs/summary`);
      if (!response.ok) throw new Error();
      const data = await response.json();
      setLabSummary(data.points || []);
    } catch {
      setLabSummary([]);
    }
  }

  async function loadRecentSessions() {
    try {
      const response = await apiFetch(`${API_URL}/api/documents/v2/sessions`);
      if (!response.ok) throw new Error();
      const data = await response.json();
      setRecentSessions(data.sessions || []);
    } catch {
      setRecentSessions([]);
    }
  }

  async function loadSystemStatus() {
    try {
      const response = await apiFetch(`${API_URL}/api/system/status`);
      if (!response.ok) throw new Error();
      setSystemStatus(await response.json());
    } catch {
      setSystemStatus(null);
    }
  }

  async function sendQuestion(event?: FormEvent, preset?: string) {
    event?.preventDefault();
    const text = (preset ?? question).trim();
    if (!text || loadingStage) return;
    handleViewChange("conversation"); setQuestion(""); setError(""); setLoadingStage("Checking safety...");
    const nextHistory = [...messages, { role: "user" as const, content: text }];
    setMessages(nextHistory); setAnswer(""); setAnswerStatus(""); setSources([]);
    try {
      const response = await apiFetch(`${API_URL}/api/chat/stream`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text, history: messages, answer_detail: answerDetail, reading_level: readingLevel }) });
      if (!response.ok || !response.body) { const data = await response.json().catch(() => ({})); throw new Error(data?.error?.message || data.detail || "The local AI service is unavailable."); }
      let finalAnswer = ""; let finalSources: Source[] = []; let finalStatus: AnswerStatus = "answered";
      for await (const event of readSseEvents(response)) {
        if (event.type === "stage") setLoadingStage(event.stage + "...");
        else if (event.type === "sources") { setSources(event.sources); setLoadingStage("Writing a cited answer..."); }
        else if (event.type === "delta") { setStreaming(true); setLoadingStage(""); setAnswer((current) => current + event.text); }
        else if (event.type === "done") { finalAnswer = event.answer; finalSources = event.sources; finalStatus = event.status; }
      }
      setAnswer(finalAnswer || "No answer was returned."); setSources(finalSources); setAnswerStatus(finalStatus);
      setMessages([...nextHistory, { role: "assistant", content: finalAnswer || "" }]);
    } catch (err) {
      if (!API_URL) setError(API_CONFIGURATION_MESSAGE);
      else if (err instanceof Error && err.message && err.message !== "Failed to fetch") setError(err.message);
      else setError("MediGuide could not reach the local AI service.");
      setMessages(messages);
    }
    finally { setLoadingStage(""); setStreaming(false); }
  }

  async function postDocumentUpload(file: File): Promise<DocUploadResult> {
    if (!API_URL) {
      throw new Error("AI service URL is not configured.");
    }

    const formData = new FormData();
    formData.append("file", file);

    let response: Response;
    try {
      response = await apiFetch(`${API_URL}/api/documents/v2/upload`, {
        method: "POST",
        body: formData,
      });
    } catch {
      throw new Error(
        `Cannot reach the MediGuide API at ${API_URL}. Start FastAPI with: .\\.venv\\Scripts\\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload`,
      );
    }

    if (!response.ok) {
      const apiError = await parseApiError(response, "MediGuide could not upload the document.");
      throw new Error(apiError.message);
    }

    return response.json() as Promise<DocUploadResult>;
  }

  async function processDocument(documentId: string): Promise<DocState> {
    if (!API_URL) {
      throw new Error("AI service URL is not configured.");
    }

    const statusLabels: Record<string, string> = {
      uploaded: "Preparing page previews...",
      queued: "Queued for document processing...",
      rendering: "Preparing page previews...",
      extracting: "Reading document text...",
      review_required: "Preparing review...",
      failed: "Document processing failed",
    };

    // A poll can still be in flight when processing finishes; once stopped,
    // its late answer must not put a stale "Preparing review..." stage back
    // (that left the review stuck with Confirm disabled).
    let pollingStopped = false;
    const pollStatus = window.setInterval(async () => {
      try {
        const statusResponse = await apiFetch(`${API_URL}/api/documents/v2/${documentId}/status`);
        if (pollingStopped || !statusResponse.ok) return;
        const status = (await statusResponse.json()) as {
          status?: string;
          filename?: string;
          stage?: string;
          retry_attempt?: number;
          retry_max?: number;
        };
        if (pollingStopped) return;
        const label = statusLabels[status.status || ""] || "Processing document...";
        setLoadingStage(label);
        setProcessStage(mapStatusToProcessStage(status.status || "", label));
        setProcessRetry(
          status.stage === "waiting_for_service" && status.retry_max
            ? { attempt: status.retry_attempt || 0, max: status.retry_max }
            : null,
        );
      } catch {
        /* polling is best-effort */
      }
    }, 1200);
    const pollTimer = pollStatus;

    try {
      const response = await fetchWithTimeout(
        `${API_URL}/api/documents/v2/${documentId}/process`,
        { method: "POST" },
        VISION_PROCESS_TIMEOUT_MS,
      );

      if (!response.ok) {
        const apiError = await parseApiError(response, "MediGuide could not read this document.");
        throw new Error(apiError.message);
      }

      return response.json() as Promise<DocState>;
    } finally {
      pollingStopped = true;
      if (pollTimer) window.clearInterval(pollTimer);
      setProcessRetry(null);
    }
  }

  async function loadSampleLabReport(options?: { guided?: boolean }) {
    if (!API_URL) {
      setError(API_CONFIGURATION_MESSAGE);
      handleViewChange("documents");
      return;
    }
    try {
      handleViewChange("documents");
      setError("");
      setDocErrorKind("");
      if (options?.guided) {
        setDemoGuide("Step 1 of 4 — Verification: Review extracted lab information, then confirm. Synthetic Jan / Apr / Aug 2026 values only.");
      } else {
        setDemoGuide("");
      }
      setLoadingStage("Preparing synthetic reports...");
      const response = await fetchWithTimeout(`${API_URL}/api/documents/v2/sample/lab-report`);
      if (!response.ok) {
        const apiError = await parseApiError(response, "We couldn't prepare the synthetic reports.");
        throw new Error(apiError.message);
      }
      const blob = await response.blob();
      const file = new File([blob], "sample-lab-report.pdf", { type: "application/pdf" });
      setLoadingStage("");
      await uploadDocument(file);
      if (options?.guided) {
        setDemoGuide("Step 1 of 4 — Verification: Review extracted lab information on each page, then confirm. Next: Labs.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "We couldn't prepare the synthetic reports.");
      setDocErrorKind("sample");
      setLoadingStage("");
    }
  }

  async function runSyntheticDocumentDemo() {
    await loadSampleLabReport({ guided: true });
  }

  async function uploadDocument(file: File) {
    handleViewChange("documents");
    setError("");
    setDocErrorKind("");
    setDocumentDragging(false);
    setDocState(null);
    setDocFields([]);
    setDocConfirmed(false);
    setDocReviewChecked(false);
    setDocExplain(null);
    setDocQuestion("");
    setAddConfirmedLabsHint("");
    setPendingDocId(null);
    setProcessFailed(false);
    setProcessStage("upload");
    setFieldReviewState({});
    setDocOriginalFields([]);
    setDraftStatus("idle");
    setPreviewZoom(1);
    setSourceBreadcrumb("");

    let uploadedId: string | null = null;

    try {
      setLoadingStage("Uploading document...");
      setProcessStage("upload");
      const uploaded = await postDocumentUpload(file);
      uploadedId = uploaded.document_id;
      pushToast("Document uploaded", "success");
      // Give the new document a stable URL as soon as it exists, the same
      // way opening an existing one does — not just React state.
      router.push(`/workspace/documents/${uploadedId}`);

      setPendingDocId(uploaded.document_id);
      setDocState({
        document_id: uploaded.document_id,
        filename: uploaded.filename,
        page_count: 0,
        status: "uploaded",
        pages: [],
        fields: [],
        confirmed: false,
      });
      setLoadingStage("File validated · Preparing page previews...");
      setProcessStage("validate");

      const processed = await processDocument(uploaded.document_id);
      setLoadingStage("Reading document text...");
      setProcessStage("read");
      setDocState(processed);
      loadReviewSession(processed);
      setDocSelectedPage(1);
      setProcessStage("extract");
      setPendingDocId(null);
      setProcessStage("review");
      setLoadingStage("");
      setProcessStage(null);
      setProcessFailed(false);
      pushToast("Extraction complete — review required", "success");
    } catch (err) {
      setProcessFailed(true);
      setDocErrorKind(uploadedId ? "extract" : "upload");
      if (!API_URL) {
        setError(API_CONFIGURATION_MESSAGE);
      } else if (err instanceof Error && err.message && err.message !== "Failed to fetch") {
        setError(err.message);
      } else if (uploadedId) {
        setError("Your original file is still available. MediGuide could not finish reading its contents.");
      } else {
        setError("MediGuide could not upload this file. The document has not been stored.");
      }
      setLoadingStage("");
      if (!uploadedId) setProcessStage(null);
    }
  }

  async function retryDocumentExtraction() {
    if (!pendingDocId && !docState?.document_id) return;
    const documentId = pendingDocId || docState!.document_id;
    setError("");
    setDocErrorKind("");
    setProcessFailed(false);
    setLoadingStage("Reading document text...");
    setProcessStage("read");
    try {
      const processed = await processDocument(documentId);
      setDocState(processed);
      loadReviewSession(processed);
      setDocSelectedPage(1);
      setLoadingStage("");
      setProcessStage(null);
      pushToast("Extraction complete — review required", "success");
    } catch (err) {
      setProcessFailed(true);
      setDocErrorKind("extract");
      setError(
        err instanceof Error && err.message !== "Failed to fetch"
          ? err.message
          : "Your original file is still available. MediGuide could not finish reading its contents.",
      );
      setLoadingStage("");
    }
  }

  // Re-reads an unconfirmed PDF with the current extraction logic (used for
  // sessions read by an older extractor). The server refuses confirmed
  // documents, so verified records can't be overwritten.
  async function rereadDocument() {
    if (!docState || docConfirmed) return;
    setError(""); setDocErrorKind("");
    setLoadingStage("Re-reading document with the current extraction...");
    setProcessStage("read");
    try {
      const response = await fetchWithTimeout(`${API_URL}/api/documents/v2/${docState.document_id}/reextract`, { method: "POST" }, VISION_PROCESS_TIMEOUT_MS);
      if (!response.ok) {
        const apiError = await parseApiError(response, "MediGuide could not re-read this document.");
        throw new Error(apiError.message);
      }
      const processed: DocState = await response.json();
      setDocState(processed);
      loadReviewSession(processed);
      setDocSelectedPage(1);
      pushToast("Document re-read — review required", "success");
    } catch (err) {
      setError(err instanceof Error && err.message !== "Failed to fetch" ? err.message : "MediGuide could not re-read this document. Your original file is still available.");
    } finally {
      setLoadingStage("");
      setProcessStage(null);
    }
  }

  async function inspectDocument(documentId: string, pageNumber: number, fieldId?: string) {
    setError("");
    setDocErrorKind("");
    setHighlightedFieldId(fieldId || null);
    setPreviewZoom(1);
    if (demoGuide) {
      setDemoGuide("Step 3 of 4 — Source-page drill-down: The highlighted field is the lab value provenance chain. Optional next: Get AI explanation for approved-source citations.");
    }
    try {
      setLoadingStage("Opening source document...");
      const response = await apiFetch(`${API_URL}/api/documents/v2/${documentId}`);
      if (response.ok) {
        const data = (await response.json()) as DocState;
        setPendingDocId(data.document_id);
        setDocState(data);
        loadReviewSession(data);
        setDocConfirmed(data.confirmed);
        setDocSelectedPage(pageNumber || 1);
        setDocExplain(null);
        // Only a drill-down to a saved value's source gets a way back.
        setSourceBreadcrumb(fieldId ? `Source of a saved value · ${data.filename || "Document"} · Page ${pageNumber || 1}` : "");
        // A stable, bookmarkable URL per document — not just "documents" —
        // so cross-links (Labs, Timeline, Ask citations, search) and page
        // refreshes land back on the same open document AND the same page/
        // field, not just the document's page 1. documents/[id]/page.tsx
        // reads these same params back on mount.
        {
          const urlParams = new URLSearchParams();
          if (pageNumber) urlParams.set("page", String(pageNumber));
          if (fieldId) urlParams.set("field", fieldId);
          const query = urlParams.toString();
          router.push(`/workspace/documents/${data.document_id}${query ? `?${query}` : ""}`);
        }
        if (!data.fields?.length && data.status !== "confirmed") {
          setLoadingStage("Reading document text...");
          const processed = await processDocument(documentId);
          setDocState(processed);
          loadReviewSession(processed);
          setDocSelectedPage(pageNumber || 1);
        }
      } else if (response.status === 404) {
        setError("This document isn't available. It may have been deleted, or it belongs to a different account.");
        handleViewChange("documents");
      } else {
        throw new Error("Could not open this document.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open this document.");
      handleViewChange("documents");
    } finally {
      setLoadingStage("");
    }
  }

  function prepareVisitFromDocument() {
    const filename = docState?.filename || "my recent lab results";
    setVisitFields({
      ...visitFields,
      "Main concern": visitFields["Main concern"] || `Understanding ${filename} before my appointment`,
      "Questions for clinician": suggestClinicianQuestions(docFields, medFields, labSummary),
    });
    setVisitStep(3);
    handleViewChange("visit");
  }

  function prepareVisitFromMedication() {
    const name = medFields.find((field) => field.key === "medication_name" || field.key === "name")?.value || "this medication";
    const strength = medFields.find((field) => field.key === "strength")?.value || "";
    setVisitFields({
      ...visitFields,
      "Medications as entered": [name, strength].filter(Boolean).join(" "),
      "Questions for clinician": suggestClinicianQuestions(docFields, medFields, labSummary),
    });
    setVisitStep(2);
    handleViewChange("visit");
  }

  function addLabsToVisit() {
    const latest = labSummary.length ? labSummary : labPoints;
    if (!latest.length) {
      handleViewChange("visit");
      return;
    }
    setVisitFields({
      ...visitFields,
      "Main concern": visitFields["Main concern"] || "Understanding my recent lab results before my appointment",
      "Questions for clinician": suggestClinicianQuestions(docFields, medFields, latest),
    });
    setVisitStep(3);
    handleViewChange("visit");
  }

  function exportLabPoints() {
    const rows = [
      ["Test", "Name on report", "Value", "Unit", "Printed range", "Report flag", "Date", "Date type", "Document", "Page", "Review", "Change", "Note"],
      ...labPoints.map((point) => [
        point.test_name,
        point.original_name || point.test_name,
        point.value_text,
        point.unit,
        point.reference_range || point.reference_text || "",
        point.source_flag || "",
        point.date || point.collection_date || point.report_date || "",
        point.date_source === "collection" ? "Collected" : point.date ? "Report date" : "",
        point.document_name,
        String(point.page_number),
        point.review_status || point.verification_state,
        point.change_from_previous == null ? "" : String(point.change_from_previous),
        point.duplicate_of ? `Same result as in ${point.duplicate_document_name || "another report"}` : "",
      ]),
    ];
    downloadCsv(`mediguide-${selectedLabCode}-timeline.csv`, rows);
  }

  function exportDocumentFields() {
    const rows = [
      ["Label", "Value", "Unit", "Reference range", "Status", "Page"],
      ...docFields.map((field) => [field.label, field.value, field.unit, field.reference_range, field.status, String(field.page_number)]),
    ];
    downloadCsv(`${docState?.filename || "document"}-extracted-fields.csv`, rows);
  }

  function askAboutDocument() {
    const lines = docFields.filter((field) => field.value).slice(0, 8).map((field) => `${field.label}: ${field.value} ${field.unit}`.trim());
    setQuestion(`Help me prepare questions about these confirmed document values:\n\n${lines.join("\n")}`);
    handleViewChange("conversation");
  }

  function suggestDocumentQuestions() {
    const suggested = suggestClinicianQuestions(docFields, medFields, labSummary);
    setDocQuestion(suggested);
  }

  function askAboutLabs() {
    const latest = labSummary.length ? labSummary : labPoints;
    const lines = latest.map((point) => `${point.test_name}: ${point.value_text} ${point.unit}${(point.date || point.report_date) ? ` (${point.date || point.report_date})` : ""}`);
    setQuestion(`Help me understand these verified lab observations educationally:\n\n${lines.join("\n")}`);
    handleViewChange("conversation");
  }

  function confirmTranscript() {
    if (!transcriptReviewed || !pendingTranscript.trim()) return;
    setQuestion(pendingTranscript.trim());
    setPendingTranscript("");
    setTranscriptReviewed(false);
  }

  async function deleteLabObservation(observationId: string) {
    try {
      const response = await apiFetch(`${API_URL}/api/labs/observations/${observationId}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Could not delete this observation.");
      setSelectedLabPoint(null);
      setConfirmDeleteObservationId(null);
      await loadLabs(selectedLabCode);
      await loadLabSummary();
      pushToast("Result removed from timeline", "success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete this observation.");
      pushToast("Could not delete this result", "error");
    }
  }

  function loadReviewSession(state: DocState) {
    const { fields, review } = applyReviewDraft(state);
    setDocOriginalFields(state.fields || []);
    setDocFields(fields);
    setFieldReviewState(review);
    lastSavedDraft.current = JSON.stringify(buildReviewDraft(fields, state.fields || [], review));
    confirmingDocument.current = false;
    setDraftStatus(state.review_draft_saved_at ? "saved" : "idle");
  }

  // Called when a correction is saved, not on every keystroke. Saving values
  // that match what was extracted counts as confirming them.
  function updateDocField(fieldId: string, patch: ReviewablePatch) {
    const current = docFields.find((field) => field.field_id === fieldId);
    if (!current) return;
    const original = docOriginalFields.find((field) => field.field_id === fieldId);
    const next = { ...current, ...patch };
    const changed = original ? REVIEWABLE_KEYS.some((key) => next[key] !== original[key]) : true;
    setDocFields((fields) => fields.map((field) => (field.field_id === fieldId ? { ...next, user_edited: changed || Boolean(original?.user_edited) } : field)));
    setFieldReviewState((review) => ({ ...review, [fieldId]: changed ? "corrected" : "confirmed" }));
  }

  function setFieldDecision(fieldIds: string[], decision: "confirmed" | "rejected") {
    setFieldReviewState((review) => {
      const next = { ...review };
      for (const id of fieldIds) next[id] = decision;
      return next;
    });
  }

  // Back to undecided, with the values as originally extracted.
  function undoFieldReview(fieldId: string) {
    const original = docOriginalFields.find((field) => field.field_id === fieldId);
    if (original) setDocFields((fields) => fields.map((field) => (field.field_id === fieldId ? original : field)));
    setFieldReviewState((review) => ({ ...review, [fieldId]: "unverified" }));
  }

  function openLabTimeline(testCode?: string) {
    if (testCode) setSelectedLabCode(testCode);
    setSelectedLabPoint(null);
    handleViewChange("labs");
    void loadLabs(testCode || selectedLabCode);
    void loadLabSummary();
  }

  async function confirmDocument() {
    if (!docState || !docReviewChecked || !docFields.length) return;
    // Every value needs a decision; nothing is confirmed by default.
    if (docFields.some((field) => (fieldReviewState[field.field_id] || "unverified") === "unverified")) return;
    setError(""); setDocErrorKind(""); setLoadingStage("Saving your reviewed values...");
    confirmingDocument.current = true;
    try {
      const response = await apiFetch(`${API_URL}/api/documents/v2/${docState.document_id}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Rejected fields are sent so the server leaves them out of the confirmed record and Labs.
        body: JSON.stringify({
          fields: docFields,
          reviewed_names_values_units_dates: true,
          excluded_field_ids: docFields.filter((field) => fieldReviewState[field.field_id] === "rejected").map((field) => field.field_id),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error?.message || data.detail || "Could not confirm this document.");
      setDocFields(data.fields || docFields); setDocConfirmed(true);
      pushToast("Results confirmed", "success");
      const labCount = data.persistence?.lab_observation_count ?? 0;
      const trackedCodes = (data.persistence?.tracked_test_codes as string[] | undefined) || [];
      setConfirmedLabCodes(trackedCodes);
      if (labCount > 0) {
        setAddConfirmedLabsHint(`${labCount} lab observation${labCount === 1 ? "" : "s"} saved to Labs.`);
        if (trackedCodes.length) setSelectedLabCode(trackedCodes.includes("hemoglobin_a1c") ? "hemoglobin_a1c" : trackedCodes[0]);
        void loadLabs(trackedCodes.includes("hemoglobin_a1c") ? "hemoglobin_a1c" : trackedCodes[0] || selectedLabCode);
        void loadLabSummary();
        void loadRecentSessions();
        if (demoGuide) {
          setDemoGuide("Step 2 of 4 — Labs: Open Labs, click 6.7%, then View source page. Optional next: Get AI explanation for approved-source citations.");
        }
      } else {
        setAddConfirmedLabsHint("");
        setConfirmedLabCodes([]);
      }
      if (data.persistence && data.persistence.persisted === false) {
        setError("Values were confirmed in this session, but Labs could not be updated. Check System status, then try confirming again.");
        setDocErrorKind("confirm");
      }
    } catch (err) {
      confirmingDocument.current = false;
      setDocErrorKind("confirm");
      if (!API_URL) setError(API_CONFIGURATION_MESSAGE);
      else if (err instanceof Error && err.message && err.message !== "Failed to fetch") setError(err.message);
      else setError("Document confirmation is unavailable right now. Check System status, then try again.");
    } finally {
      setLoadingStage("");
    }
  }

  async function explainDocument() {
    if (!docState || !docConfirmed) return;
    setError(""); setDocErrorKind(""); setDocExplain(null); setLoadingStage("Finding evidence and writing an explanation...");
    try {
      const response = await apiFetch(`${API_URL}/api/documents/v2/${docState.document_id}/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: docQuestion.trim() || undefined }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error?.message || data.detail || "Could not generate an explanation.");
      setDocExplain(data);
      if (demoGuide) {
        setDemoGuide("Step 4 of 4 — Source Evidence: Citations in the explanation link to approved educational sources. Lab values still drill back to the original report page.");
      }
    } catch (err) {
      setDocErrorKind("explain");
      if (!API_URL) setError(API_CONFIGURATION_MESSAGE);
      else if (err instanceof Error && err.message && err.message !== "Failed to fetch") setError(err.message);
      else setError("Document explanation is unavailable right now. Check System status, then try again.");
    } finally {
      setLoadingStage("");
    }
  }

  async function deleteDocument() {
    const documentId = docState?.document_id;
    // Demo-mode documents only ever existed in this browser.
    if (documentId && !documentId.startsWith("demo-")) {
      try {
        const response = await apiFetch(`${API_URL}/api/documents/v2/${documentId}`, { method: "DELETE" });
        if (!response.ok && response.status !== 404) {
          const failure = await parseApiError(response, "This document could not be deleted.");
          pushToast(failure.message, "error");
          return false;
        }
      } catch {
        pushToast("This document could not be deleted. Check your connection and try again.", "error");
        return false;
      }
    }
    resetDocument();
    void loadRecentSessions();
    void loadLabSummary();
    return true;
  }

  function resetDocument() {
    setDocOriginalFields([]); setDraftStatus("idle"); lastSavedDraft.current = ""; confirmingDocument.current = false;
    setDocState(null); setDocFields([]); setDocConfirmed(false); setDocReviewChecked(false); setDocExplain(null); setDocQuestion(""); setDocSelectedPage(1); setError(""); setDocErrorKind(""); setAddConfirmedLabsHint(""); setConfirmedLabCodes([]); setPendingDocId(null); setHighlightedFieldId(null);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) { event.preventDefault(); setDocumentDragging(false); const file = event.dataTransfer.files[0]; if (file) void uploadDocument(file); }
  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    void uploadDocument(file);
    event.target.value = "";
  }

  function resetMedication() {
    setMedState(null); setMedFields([]); setMedConfirmed(false); setMedReviewChecked(false); setMedInfo(null); setMedQuestion(""); setMedTypedText(""); setError("");
  }

  async function uploadMedication(file: File) {
    handleViewChange("medication"); setError(""); setMedDragging(false);
    resetMedication();
    setLoadingStage("Reading the medication label...");
    const form = new FormData(); form.append("file", file);
    try {
      const response = await fetchWithTimeout(`${API_URL}/api/medications/v2/upload`, { method: "POST", body: form }, VISION_PROCESS_TIMEOUT_MS);
      if (!response.ok) {
        const apiError = await parseApiError(response, "MediGuide could not read that label.");
        throw new Error(apiError.message);
      }
      const data = await response.json();
      applyMedState(data);
    } catch (err) {
      if (!API_URL) setError(API_CONFIGURATION_MESSAGE);
      else if (err instanceof Error && err.message && err.message !== "Failed to fetch") setError(err.message);
      else setError("MediGuide could not read that label. Check the file and try again.");
    } finally {
      setLoadingStage("");
    }
  }

  async function submitTypedMedication(text: string) {
    if (!text.trim()) return;
    handleViewChange("medication"); setError("");
    setMedState(null); setMedFields([]); setMedConfirmed(false); setMedReviewChecked(false); setMedInfo(null); setMedQuestion("");
    setLoadingStage("Reading the medication label text...");
    try {
      const response = await fetchWithTimeout(`${API_URL}/api/medications/v2/text`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) }, VISION_PROCESS_TIMEOUT_MS);
      if (!response.ok) {
        const apiError = await parseApiError(response, "MediGuide could not read that label text.");
        throw new Error(apiError.message);
      }
      const data = await response.json();
      applyMedState(data);
    } catch (err) {
      if (!API_URL) setError(API_CONFIGURATION_MESSAGE);
      else if (err instanceof Error && err.message && err.message !== "Failed to fetch") setError(err.message);
      else setError("MediGuide could not read that label text. Please try again.");
    } finally {
      setLoadingStage("");
    }
  }

  // A medication session from the server: the details used elsewhere (visit
  // prep, questions) are those of the first confirmed medication.
  function applyMedState(state: MedState) {
    const entries = state.entries || [];
    const confirmedEntry = entries.find((entry) => entry.decision === "confirmed");
    setMedState(state);
    setMedFields(confirmedEntry?.fields || entries[0]?.fields || state.fields || []);
    setMedConfirmed(Boolean(confirmedEntry) || (!entries.length && state.confirmed));
  }

  function updateMedField(key: string, value: string) {
    setMedFields((current) => current.map((field) => (field.key === key ? { ...field, value, user_edited: true } : field)));
  }

  async function confirmMedication() {
    if (!medState || !medReviewChecked || !medFields.length) return;
    setError(""); setLoadingStage("Saving your reviewed details...");
    try {
      const response = await apiFetch(`${API_URL}/api/medications/v2/${medState.medication_id}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fields: medFields, reviewed_name_strength_instructions: true }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error?.message || data.detail || "Could not confirm this medication.");
      setMedFields(data.fields || medFields); setMedConfirmed(true);
    } catch (err) {
      if (!API_URL) setError(API_CONFIGURATION_MESSAGE);
      else if (err instanceof Error && err.message && err.message !== "Failed to fetch") setError(err.message);
      else setError("MediGuide could not confirm this medication. Please try again.");
    } finally {
      setLoadingStage("");
    }
  }

  async function getMedicationInfo() {
    if (!medState || !medConfirmed) return;
    setError(""); setMedInfo(null); setLoadingStage("Finding evidence and writing educational information...");
    try {
      const response = await apiFetch(`${API_URL}/api/medications/v2/${medState.medication_id}/info`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: medQuestion.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error?.message || data.detail || "Could not generate medication information.");
      setMedInfo(data);
    } catch (err) {
      if (!API_URL) setError(API_CONFIGURATION_MESSAGE);
      else if (err instanceof Error && err.message && err.message !== "Failed to fetch") setError(err.message);
      else setError("MediGuide could not generate information for this medication.");
    } finally {
      setLoadingStage("");
    }
  }

  function onMedDrop(event: DragEvent<HTMLDivElement>) { event.preventDefault(); setMedDragging(false); const file = event.dataTransfer.files[0]; if (file) void uploadMedication(file); }
  function onMedFileChange(event: ChangeEvent<HTMLInputElement>) { const file = event.target.files?.[0]; if (file) void uploadMedication(file); }

  async function toggleVoice() {
    if (recording) { recorder.current?.stop(); setRecording(false); setLoadingStage("Creating transcript..."); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true }); const next = new MediaRecorder(stream); audioChunks.current = [];
      next.ondataavailable = (event) => audioChunks.current.push(event.data);
        next.onstop = async () => {
          stream.getTracks().forEach((track) => track.stop());
          const form = new FormData();
          form.append("file", new Blob(audioChunks.current, { type: "audio/webm" }), "question.webm");
          try {
            const response = await apiFetch(`${API_URL}/api/transcribe`, { method: "POST", body: form });
            const data = await response.json();
            if (!response.ok) throw new Error();
            setPendingTranscript(data.text || "");
            setTranscriptReviewed(false);
            handleViewChange("conversation");
          } catch {
            setError("MediGuide could not create a transcript. Your audio was not sent.");
          } finally {
            setLoadingStage("");
          }
        };
      recorder.current = next; next.start(); setRecording(true); setLoadingStage("Listening locally...");
    } catch { setError("Microphone access was not available. Your question has not been sent."); }
  }

  function handleComposerKey(event: KeyboardEvent<HTMLTextAreaElement>) { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendQuestion(); } }
  function clearSession() { setMessages([]); setAnswer(""); setAnswerStatus(""); setQuestion(""); setSources([]); resetDocument(); resetMedication(); handleViewChange("conversation"); }
  function retry() { const last = [...messages].reverse().find((item) => item.role === "user"); if (last) void sendQuestion(undefined, last.content); }
  function copyAnswer() { if (answer) void navigator.clipboard?.writeText(answer); }
  function readAnswer() { if (!answer) return; void apiFetch(`${API_URL}/api/speak`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: answer.replace(/[#*_\[\]]/g, "") }) }).then(async (response) => { if (!response.ok) throw new Error(); const audio = new Audio(URL.createObjectURL(await response.blob())); await audio.play(); }).catch(() => setError("Spoken output is unavailable right now.")); }
  async function translateAnswer(target: string) { if (!answer) return; setLoadingStage(`Translating to ${target}...`); try { const response = await apiFetch(`${API_URL}/api/translate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: answer, language: target }) }); const data = await response.json(); if (!response.ok) throw new Error(); setAnswer(data.text || answer); setLanguage(target); } catch { setError("MediGuide could not translate this answer right now."); } finally { setLoadingStage(""); } }
  function generateVisitSummary() { const summary = Object.entries(visitFields).filter(([, value]) => value.trim()).map(([key, value]) => `${key}: ${value}`).join("\n\n"); setQuestion(`Help me prepare questions for a healthcare professional using these patient-provided notes:\n\n${summary}`); handleViewChange("conversation"); }

  const handleViewChange = (nextView: View) => { router.push(`/workspace/${VIEW_TO_PATH[nextView]}`); setMobileNavOpen(false); };

  function openDocumentPage(pageNumber: number) {
    setDocSelectedPage(pageNumber);
    if (docState?.document_id) router.push(`/workspace/documents/${docState.document_id}`);
    else handleViewChange("documents");
  }

  function retryDocumentAction() {
    if (docErrorKind === "extract") void retryDocumentExtraction();
    else if (docErrorKind === "confirm") void confirmDocument();
    else if (docErrorKind === "explain") void explainDocument();
    else if (docErrorKind === "sample") void loadSampleLabReport({ guided: demoGuide !== "" });
    else fileInput.current?.click();
  }

  // The sample label goes through the same typed-label endpoint a person
  // would use, so it is a real, owned session that can be confirmed and
  // explained (a client-only fixture with a fake id 404'd on confirm).
  function loadDemoMedication() {
    void submitTypedMedication(DEMO_MEDICATION_LABEL_TEXT);
  }

  const docEvidenceSources: Source[] = (docExplain?.sources || []).map((source) => ({ number: source.citation_number, title: source.title, publisher: source.publisher, url: source.source_url, passage: source.passage }));
  const medEvidenceSources: Source[] = (medInfo?.sources || []).map((source) => ({ number: source.citation_number, title: source.title, publisher: source.publisher, url: source.source_url, passage: source.passage }));
  const evidenceSources = view === "documents" && docExplain ? docEvidenceSources : view === "medication" && medInfo ? medEvidenceSources : sources;
  const evidenceContext: "document-review" | "explaining" | "chat" | "idle" = view === "documents" && !docExplain ? "document-review" : view === "documents" && docExplain ? "explaining" : view === "medication" && medInfo ? "explaining" : sources.length ? "chat" : "idle";

  return {
    router,
    mobileNavOpen, setMobileNavOpen,
    view,
    messages, setMessages,
    answer, setAnswer,
    answerStatus, setAnswerStatus,
    streaming, setStreaming,
    question, setQuestion,
    sources, setSources,
    loadingStage, setLoadingStage,
    error, setError,
    health, setHealth,
    healthOpen, setHealthOpen,
    privacyOpen, setPrivacyOpen,
    settingsOpen, setSettingsOpen,
    helpOpen, setHelpOpen,
    pendingTranscript, setPendingTranscript,
    transcriptReviewed, setTranscriptReviewed,
    selectedSource, setSelectedSource,
    language, setLanguage,
    recording, setRecording,
    docState, setDocState,
    docFields, setDocFields,
    docConfirmed, setDocConfirmed,
    docReviewChecked, setDocReviewChecked,
    docSelectedPage, setDocSelectedPage,
    docExplain, setDocExplain,
    docQuestion, setDocQuestion,
    documentDragging, setDocumentDragging,
    medState, setMedState, applyMedState,
    medFields, setMedFields,
    medConfirmed, setMedConfirmed,
    medReviewChecked, setMedReviewChecked,
    medInfo, setMedInfo,
    medQuestion, setMedQuestion,
    medTypedText, setMedTypedText,
    medDragging, setMedDragging,
    visitFields, setVisitFields,
    visitStep, setVisitStep,
    addConfirmedLabsHint, setAddConfirmedLabsHint,
    demoGuide, setDemoGuide,
    confirmedLabCodes, setConfirmedLabCodes,
    docErrorKind, setDocErrorKind,
    pendingDocId, setPendingDocId,
    highlightedFieldId, setHighlightedFieldId,
    processStage, setProcessStage,
    processFailed, setProcessFailed,
    processRetry,
    toasts, setToasts,
    confirmDeleteObservationId, setConfirmDeleteObservationId,
    confirmResetDocument, setConfirmResetDocument,
    sourceBreadcrumb, setSourceBreadcrumb,
    previewZoom, setPreviewZoom,
    fieldReviewState, setFieldReviewState,
    docOriginalFields,
    draftStatus,
    setFieldDecision,
    undoFieldReview,
    labTests, setLabTests,
    selectedLabCode, setSelectedLabCode,
    labPoints, setLabPoints,
    labSummary, setLabSummary,
    recentSessions, setRecentSessions,
    selectedLabPoint, setSelectedLabPoint,
    systemStatus, setSystemStatus,
    answerDetail, setAnswerDetail,
    readingLevel, setReadingLevel,
    fileInput,
    medFileInput,
    pushToast,
    checkHealth,
    loadLabs,
    loadLabSummary,
    loadRecentSessions,
    loadSystemStatus,
    sendQuestion,
    loadSampleLabReport,
    runSyntheticDocumentDemo,
    uploadDocument,
    retryDocumentExtraction,
    rereadDocument,
    inspectDocument,
    prepareVisitFromDocument,
    prepareVisitFromMedication,
    addLabsToVisit,
    exportLabPoints,
    exportDocumentFields,
    askAboutDocument,
    suggestDocumentQuestions,
    askAboutLabs,
    confirmTranscript,
    deleteLabObservation,
    updateDocField,
    openLabTimeline,
    confirmDocument,
    explainDocument,
    resetDocument,
    deleteDocument,
    onDrop,
    onFileChange,
    resetMedication,
    uploadMedication,
    submitTypedMedication,
    updateMedField,
    confirmMedication,
    getMedicationInfo,
    onMedDrop,
    onMedFileChange,
    toggleVoice,
    handleComposerKey,
    clearSession,
    retry,
    copyAnswer,
    readAnswer,
    translateAnswer,
    generateVisitSummary,
    handleViewChange,
    openDocumentPage,
    retryDocumentAction,
    loadDemoMedication,
    evidenceSources,
    evidenceContext,
  };
}

type WorkspaceContextValue = ReturnType<typeof useWorkspaceState>;

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceStateProvider({ children }: { children: ReactNode }) {
  const value = useWorkspaceState();
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspaceContext(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspaceContext must be used within a WorkspaceStateProvider");
  }
  return context;
}
