"use client";

import { DragEvent, FormEvent, KeyboardEvent, useEffect, useState } from "react";
import { Activity, ArrowUp, ArrowUpRight, BookOpen, Check, ChevronRight, Clipboard, FileText, FlaskConical, Image as ImageIcon, Lock, Mic, Paperclip, Pill, PlayCircle, Plus, RefreshCw, ShieldCheck, Sparkles, Stethoscope, Trash2, TrendingUp, Volume2, X } from "lucide-react";
import { EVALUATION_METRICS } from "../../lib/demo-data";
import {
  Drawer,
  EmptyState,
  Input,
  ProcessingChecklist,
  ServiceError,
  StatusChip,
  Table,
  friendlyComponentStatus,
  friendlyHealthLabel,
  mapStatusToProcessStage,
  type ProcessStageId,
} from "./polish-ui";
import { PageHero } from "./_components/PageHero";

import {
  quickActions,
  topicSuggestions,
  healthLabels,
  downloadTextFile,
  suggestClinicianQuestions,
  VISIT_STORAGE_KEY,
  type Source,
  type LibrarySource,
  type Message,
  type DocField,
  type DocState,
  type DocPage,
  type DocSession,
  type DocExplain,
  type HealthResponse,
  type MedField,
  type MedState,
  type MedInfo,
  type LabTest,
  type LabPoint,
  type SystemStatus,
  type View,
  type AnswerStatus,
  CURRENT_EXTRACTION_VERSION,
  type DraftSaveStatus,
  type FieldReviewDecision,
  type ReviewablePatch,
} from "./_state/workspace-shared";
import { DocumentReview } from "./documents/DocumentReview";
import { MedicationReview } from "./medications/MedicationReview";
import { MedicationRecords } from "./medications/MedicationRecords";
import { LabTrendChart, isPlottable } from "./_components/LabTrendChart";
export function Conversation({ aiAvailable = true, chatAvailable = true, answer, status, streaming, sources, messages, loading, error, selectedSource, setSelectedSource, onRetry, onPreset, onOpenView, onOpenDocumentPage, onUpload, onAction }: { aiAvailable?: boolean; chatAvailable?: boolean; answer: string; status: AnswerStatus; streaming: boolean; sources: Source[]; question: string; messages: Message[]; loading: string; error: string; selectedSource: number | null; setSelectedSource: (value: number | null) => void; onRetry: () => void; onPreset: (prompt: string) => void; onOpenView: (view: View) => void; onOpenDocumentPage: (page: number) => void; onUpload: () => void; onAction: (action: "copy" | "listen" | "simple" | "questions") => void }) {
  const lastQuestion = [...messages].reverse().find((item) => item.role === "user");
  const empty = !answer && !loading && !lastQuestion;
  if (!chatAvailable) {
    return <div className="conversation-view">
      <PageHero eyebrow="Educational support" title="AI answers are" accent="switched off." lead="This version of MediGuide runs without its AI model, so it can't answer questions or write explanations." />
      <EmptyState
        title="Everything else still works"
        body="Upload and review lab reports, track verified results over time, check medication labels and prepare for a visit. Nothing you confirm depends on AI answers."
      >
        <button type="button" className="forest-button" onClick={() => onOpenView("documents")}><FileText size={15} /> Review a document</button>
        <button type="button" className="quiet-button" onClick={() => onOpenView("labs")}>Open Labs</button>
        <button type="button" className="quiet-button" onClick={() => onOpenView("visit")}><Stethoscope size={15} /> Prepare for a visit</button>
      </EmptyState>
    </div>;
  }
  return <div className="conversation-view">
    <PageHero
      eyebrow="Educational support"
     
      title={answer ? "Your health question," : "What can I help you"}
      accent={answer ? "clarified." : "understand today?"}
      lead={answer ? undefined : "Ask a health question, review a document, use your voice, or prepare for an appointment — in one workspace."}
      meta={<>
        <span className="response-count">{messages.filter((message) => message.role === "user").length} session {messages.filter((message) => message.role === "user").length === 1 ? "question" : "questions"}</span>
        <span className="care-mode"><ShieldCheck size={13} /> Educational support</span>
      </>}
    />
    {!aiAvailable && <p className="demo-guide-banner" role="note">AI writing is switched off on this version of MediGuide. Answers quote the best-matching passages from approved sources, with citations, instead of writing a reply.</p>}
    {empty && <div className="capability-rail" aria-label="Workspace capabilities">
      <button type="button" onClick={() => { onPreset("What is diabetes in plain language?"); document.querySelector<HTMLTextAreaElement>(".composer textarea")?.focus(); }}>
        <span className="quick-icon"><BookOpen size={18} /></span>
        <strong>Ask with evidence</strong>
        <small>Try a topic in the approved knowledge base</small>
      </button>
      <button type="button" onClick={() => { onOpenView("documents"); onUpload(); }}>
        <span className="quick-icon"><FileText size={18} /></span>
        <strong>Review a document</strong>
        <small>Verify values before you reason</small>
      </button>
      <button type="button" onClick={() => document.querySelector<HTMLButtonElement>(".composer .voice-trigger")?.click()}>
        <span className="quick-icon"><Mic size={18} /></span>
        <strong>Speak, then confirm</strong>
        <small>Transcript review before sending</small>
      </button>
      <button type="button" onClick={() => onOpenView("visit")}>
        <span className="quick-icon"><Stethoscope size={18} /></span>
        <strong>Prepare for a visit</strong>
        <small>Turn notes into useful questions</small>
      </button>
    </div>}
    {empty && <p className="covered-topics">Demo topics include blood pressure, cholesterol, diabetes, CBC lab tests, medication labels, antibiotics, fever, allergies, and appointment preparation — plus the approved CDC/NIH sources already in the knowledge base.</p>}
    {empty && <div className="topic-chip-row" aria-label="Suggested topics">
      {topicSuggestions.map(([label, prompt]) => (
        <button type="button" key={label} onClick={() => { onPreset(prompt); void (document.querySelector<HTMLTextAreaElement>(".composer textarea")?.focus()); }}>
          {label}
        </button>
      ))}
    </div>}
    {empty && <div className="quick-actions">{quickActions.map(([title, description, Icon, prompt]) => <button key={title} onClick={() => { onPreset(prompt); document.querySelector<HTMLTextAreaElement>(".composer textarea")?.focus(); }}><span className="quick-icon"><Icon size={18} /></span><span><strong>{title}</strong><small>{description}</small></span><ChevronRight size={17} /></button>)}</div>}
    {lastQuestion && <div className="user-question"><span>You asked</span><p>{lastQuestion.content}</p></div>}
    {error && <ServiceError title="Could not reach MediGuide" message={error} onRetry={onRetry} onSystem={() => onOpenView("system")} />}
    {loading && <div className="processing"><Sparkles size={17} /><span>{loading}</span><i /><i /><i /></div>}
    {answer && <Answer answer={answer} status={status} streaming={streaming} sources={sources} selectedSource={selectedSource} setSelectedSource={setSelectedSource} onAction={onAction} onPreset={onPreset} onOpenView={onOpenView} onOpenDocumentPage={onOpenDocumentPage} onRetry={onRetry} />}
  </div>;
}

function Answer({ answer, status, streaming, sources, selectedSource, setSelectedSource, onAction, onPreset, onOpenView, onOpenDocumentPage, onRetry }: { onRetry: () => void; answer: string; status: AnswerStatus; streaming: boolean; sources: Source[]; selectedSource: number | null; setSelectedSource: (value: number | null) => void; onAction: (action: "copy" | "listen" | "simple" | "questions") => void; onPreset: (prompt: string) => void; onOpenView: (view: View) => void; onOpenDocumentPage: (page: number) => void }) {
  const body = answer.split("\n\n---\n")[0];

  if (status === "emergency") {
    return <article className="answer-document emergency-evidence">
      <div className="answer-kicker"><span><Activity size={14} /> MEDIGUIDE</span><small>Emergency signal detected</small></div>
      <div className="limited-evidence-body"><h3>This may be a medical emergency.</h3><p>{body}</p></div>
    </article>;
  }

  if (status === "no_evidence") {
    return <article className="answer-document limited-evidence">
      <div className="answer-kicker"><span><ShieldCheck size={14} /> MEDIGUIDE</span><small>Safety check</small></div>
      <div className="limited-evidence-body">
        <h3>Limited trusted information available</h3>
        <p>MediGuide couldn’t find enough approved source material to answer this question confidently.</p>
        <ul>
          <li>Ask a more specific question</li>
          <li>Review one of the available topics</li>
          <li>Add a trusted source to the knowledge base</li>
        </ul>
        <div className="topic-chip-row">
          {topicSuggestions.map(([label, prompt]) => (
            <button type="button" key={label} onClick={() => {
              if (label === "Prepare for a visit") onOpenView("visit");
              else onPreset(prompt);
            }}>{label}</button>
          ))}
        </div>
      </div>
    </article>;
  }

  if (status === "withheld" || status === "error") {
    return <article className="answer-document withheld-evidence">
      <div className="answer-kicker"><span><ShieldCheck size={14} /> MEDIGUIDE</span><small>{status === "withheld" ? "Answer withheld" : "Service error"}</small></div>
      <div className="limited-evidence-body">
        <h3>{status === "withheld" ? "This answer could not be safely shown." : "MediGuide couldn’t finish this answer."}</h3>
        <p>{body}</p>
        {status === "error" && <button type="button" className="quiet-button answer-retry" onClick={onRetry}><RefreshCw size={14} /> Try again</button>}
      </div>
    </article>;
  }

  const lines = body.split("\n");
  const renderPart = (part: string, key: string) => {
    const pageMatch = /^\[D(\d+)\]$/.exec(part);
    if (pageMatch) {
      const page = Number(pageMatch[1]);
      return <button type="button" className="doc-citation" onClick={() => onOpenDocumentPage(page)} key={key}>[D{page}]</button>;
    }
    const numbers = /^\[\d+(?:,\s*\d+)*\]$/.test(part) ? part.match(/\d+/g) : null;
    if (!numbers) return part.replace(/^#+\s*/, "");
    return numbers.map((num, index) => (
      <button className={selectedSource === Number(num) ? "citation selected" : "citation"} onClick={() => setSelectedSource(Number(num))} key={`${key}-${index}`}>[{num}]</button>
    ));
  };
  return <article className="answer-document"><div className="answer-kicker"><span><Sparkles size={14} /> MEDIGUIDE</span><small>{streaming ? "Writing..." : status === "sources_only" ? "Quoted from approved sources" : "Evidence checked"}</small></div><div className="answer-content">{lines.map((line, index) => { const heading = line.startsWith("#"); const parts = line.split(/(\[D\d+\]|\[\d+(?:,\s*\d+)*\])/g); return <p className={heading ? "answer-heading" : ""} key={index}>{parts.map((part, partIndex) => renderPart(part, `${index}-${partIndex}`))}</p>; })}{streaming && <span className="streaming-cursor" aria-hidden />}</div>{!streaming && <div className="response-actions"><button onClick={() => onAction("copy")}><Clipboard size={14} /> Copy</button><button onClick={() => onAction("listen")}><Volume2 size={14} /> Listen</button>{status !== "sources_only" && <button onClick={() => onAction("simple")}><Sparkles size={14} /> Explain simply</button>}<button onClick={() => onAction("questions")}><Stethoscope size={14} /> Questions for clinician</button><button onClick={() => setSelectedSource(sources.length ? sources[0].number : null)}><BookOpen size={14} /> Show sources</button></div>}<p className="answer-safety-note"><ShieldCheck size={13} /> General educational information, not a diagnosis or personalized treatment recommendation.</p></article>;
}

export function Composer({ question, setQuestion, onSubmit, onKeyDown, onUpload, onVoice, recording, loading, answerDetail, setAnswerDetail, readingLevel, setReadingLevel }: { question: string; setQuestion: (value: string) => void; onSubmit: (event?: FormEvent) => void; onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void; onUpload: () => void; onVoice: () => void; recording: boolean; loading: boolean; answerDetail: "Concise" | "Standard" | "Detailed"; setAnswerDetail: (value: "Concise" | "Standard" | "Detailed") => void; readingLevel: "Standard" | "Plain"; setReadingLevel: (value: "Standard" | "Plain") => void }) {
  return <form className="composer workspace-composer" onSubmit={onSubmit} onDragOver={(event) => event.preventDefault()}>
    <div className="composer-tools">
      <button type="button" onClick={onUpload}><Paperclip size={15} /> Document</button>
      <button type="button" className={recording ? "recording voice-trigger" : "voice-trigger"} onClick={onVoice}><Mic size={15} /> {recording ? "Listening locally" : "Voice"}</button>
      <select className="answer-style-select" value={answerDetail} onChange={(event) => setAnswerDetail(event.target.value as "Concise" | "Standard" | "Detailed")} aria-label="Answer detail">
        <option value="Concise">Concise answer</option><option value="Standard">Standard detail</option><option value="Detailed">Detailed answer</option>
      </select>
      <select className="answer-style-select" value={readingLevel} onChange={(event) => setReadingLevel(event.target.value as "Standard" | "Plain")} aria-label="Reading level">
        <option value="Standard">Standard reading</option><option value="Plain">Plain language</option>
      </select>
      <span className="composer-privacy"><ShieldCheck size={13} /> Private session</span>
    </div>
    <textarea aria-label="Ask MediGuide a health question" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={onKeyDown} placeholder="Ask a health question, review a document, or prepare for a visit…" rows={3} />
    <div className="composer-footer">
      <div>
        <span>Enter to send · Shift + Enter for a new line</span>
      </div>
      <button className="send-button" disabled={loading || !question.trim()} aria-label="Send"><ArrowUp size={20} /></button>
    </div>
  </form>;
}

export function Evidence({ sources, selected, onSelect, context = "idle", onOpenSources }: { sources: Source[]; selected: number | null; onSelect: (value: number | null) => void; context?: "idle" | "document-review" | "explaining" | "chat"; onOpenSources?: () => void }) {
  const showKnowledgeNote = context === "explaining" || context === "chat";
  const isExplanation = context === "explaining" || context === "chat";
  const emptyTitle = context === "document-review" ? "Sources appear with explanations" : "Citations appear beside answers";
  const emptyBody = context === "document-review"
    ? "Once your values are confirmed, ask MediGuide to explain them; the approved sources it uses appear here."
    : "Trusted evidence used in your answer will appear here.";
  const selectedSource = sources.find((source) => source.number === selected);

  return <aside className="evidence workspace-evidence">
    <div className="evidence-top">
      <div>
        <p className="eyebrow">{isExplanation ? "EXPLANATION PROVENANCE" : "SOURCE EVIDENCE"}</p>
        <h3>{isExplanation ? "Approved knowledge sources" : "Sources & context"}</h3>
      </div>
      <button className="icon-button" title="Browse approved sources" onClick={onOpenSources}><BookOpen size={17} /></button>
    </div>
    {isExplanation && sources.length > 0 && (
      <p className="provenance-chain-note">Plain-language statement → Citation → Approved knowledge source → Source/version</p>
    )}
    {sources.length ? <>
      <div className="support-level"><span>Evidence support</span><strong>{sources.length > 2 ? "STRONG" : sources.length === 2 ? "PARTIAL" : "LIMITED"}</strong></div>
      {sources.map((source) => <button className={selected === source.number ? "source-card selected" : "source-card"} key={source.number} onClick={() => onSelect(source.number)}><span className="source-number">[{source.number}]</span><span><strong>{source.publisher}</strong><b>{source.title}</b><small>{source.reviewed ? `Reviewed ${source.reviewed}` : "Approved knowledge source"}</small><em>{source.url ? "Open source" : "Relevant passage available"} <ArrowUpRight size={12} /></em></span></button>)}
      {selectedSource?.passage && <div className="evidence-passage"><p className="eyebrow">PASSAGE</p><p>{selectedSource.passage}</p></div>}
      {selectedSource?.url && <a className="quiet-button" href={selectedSource.url} target="_blank" rel="noreferrer">Open publisher page <ArrowUpRight size={14} /></a>}
    </> : <div className="evidence-empty">
      <BookOpen size={22} />
      <strong>{emptyTitle}</strong>
      <p>{emptyBody}</p>
      {context !== "document-review" && <ul className="evidence-promise">
        <li><Check size={13} /> Cited answers</li>
        <li><Check size={13} /> Local retrieval</li>
        <li><Check size={13} /> Passage context</li>
      </ul>}
      {onOpenSources && <button type="button" className="quiet-button" onClick={onOpenSources}>Browse knowledge base</button>}
    </div>}
    {showKnowledgeNote && <div className="evidence-note"><ShieldCheck size={16} /><span>Explanation provenance is separate from lab-value provenance — citations support education, not the numeric extraction.</span></div>}
  </aside>;
}


/** One consistent processing-state vocabulary for documents. */
function documentStatusChip(status: string, confirmed: boolean): { label: string; tone: "neutral" | "success" | "warning" | "error" } {
  if (confirmed || status === "confirmed") return { label: "Completed", tone: "success" };
  if (status === "failed") return { label: "Failed", tone: "error" };
  if (status === "review_required") return { label: "Needs review", tone: "warning" };
  if (status === "extracting" || status === "processing" || status === "rendering") return { label: "Processing", tone: "neutral" };
  if (status === "queued") return { label: "Queued", tone: "neutral" };
  return { label: "Uploaded", tone: "neutral" };
}

function pageReadLabel(page: DocPage): string {
  const quality = page.quality ? `${page.quality} reading quality` : "";
  if (page.text_source === "text_layer") return "Read from the PDF's text — exact characters";
  if (page.text_source === "ocr") return `Read by OCR (scanned or photographed page) · ${quality}`;
  if (page.text_source === "vision") return "Read by the AI vision model — check every value against the page";
  return "No readable text found on this page";
}

export function Documents({
  apiUrl, docState, docFields, docConfirmed, docReviewChecked, setDocReviewChecked,
  docSelectedPage, setDocSelectedPage, highlightedFieldId, setHighlightedFieldId,
  docExplain, docQuestion, setDocQuestion,
  selectedSource, setSelectedSource,
  dragging, recentSessions, onOpenSession, onUpload, onLoadSample, demoGuide, onOpenLabsFromDemo, onDrop, onDragEnter, onDragLeave, onFieldChange, onConfirm, onExplain, onSuggestQuestions, onPrepareVisit, onAskAbout, onExportFields, onOpenLabs, onReset, onReread,
  loading, error, errorKind, labsHint, confirmedLabCodes, onRetry, onSystem, onRemove, onOpenImaging,
  processStage, processFailed, processRetry, fieldReviewState, draftStatus, onDecide, onUndo, previewZoom, setPreviewZoom, sourceBreadcrumb, onClearBreadcrumb, onBackToSource,
}: {
  apiUrl: string;
  docState: DocState | null;
  docFields: DocField[];
  docConfirmed: boolean;
  docReviewChecked: boolean;
  setDocReviewChecked: (value: boolean) => void;
  docSelectedPage: number;
  setDocSelectedPage: (value: number) => void;
  highlightedFieldId: string | null;
  setHighlightedFieldId: (value: string | null) => void;
  docExplain: DocExplain | null;
  docQuestion: string;
  setDocQuestion: (value: string) => void;
  selectedSource: number | null;
  setSelectedSource: (value: number | null) => void;
  dragging: boolean;
  recentSessions: DocSession[];
  onOpenSession: (documentId: string) => void;
  onUpload: () => void;
  onLoadSample: () => void;
  demoGuide: string;
  onOpenLabsFromDemo: () => void;
  onDrop: (event: DragEvent<HTMLDivElement>) => void;
  onDragEnter: () => void;
  onDragLeave: () => void;
  onFieldChange: (fieldId: string, patch: ReviewablePatch) => void;
  onConfirm: () => void;
  /** Omitted when AI answers are unavailable; the action is then hidden. */
  onExplain?: () => void;
  onSuggestQuestions: () => void;
  onPrepareVisit: () => void;
  /** Omitted when AI answers are unavailable; the action is then hidden. */
  onAskAbout?: () => void;
  onExportFields: () => void;
  onOpenLabs: () => void;
  onReset: () => void;
  onReread: () => void;
  loading: string;
  error: string;
  errorKind: "upload" | "extract" | "confirm" | "explain" | "sample" | "";
  labsHint: string;
  confirmedLabCodes: string[];
  onRetry: () => void;
  onSystem: () => void;
  onRemove: () => void;
  onOpenImaging?: () => void;
  processStage: ProcessStageId | null;
  processFailed: boolean;
  processRetry: { attempt: number; max: number } | null;
  fieldReviewState: Record<string, FieldReviewDecision>;
  draftStatus: DraftSaveStatus;
  onDecide: (fieldIds: string[], decision: "confirmed" | "rejected") => void;
  onUndo: (fieldId: string) => void;
  previewZoom: number;
  setPreviewZoom: (value: number) => void;
  sourceBreadcrumb: string;
  onClearBreadcrumb: () => void;
  onBackToSource: () => void;
}) {
  const uploadErrorTitle = errorKind === "extract"
    ? "We couldn't finish reading this document"
    : errorKind === "confirm"
      ? "Could not save reviewed values"
      : errorKind === "explain"
        ? "Educational explanation unavailable"
        : errorKind === "sample"
          ? "We couldn't prepare the synthetic reports"
          : "Document upload failed";
  const uploadErrorMessage = errorKind === "sample"
    ? `${error || "We couldn't prepare the synthetic reports."} No personal documents were affected.`
    : error || (errorKind === "extract"
      ? "Your original file is still available."
      : "MediGuide could not upload this file. The document has not been stored.");

  if (!docState) {
    return <div className="workflow-view">
      <PageHero
        eyebrow="Documents"
        title="Documents"
        lead="Upload, review, and trace information from your health documents."
        actions={<>
          <button className="forest-button" type="button" onClick={onUpload}><Plus size={15} /> Upload document</button>
          <button className="quiet-button" type="button" onClick={onLoadSample}>Try synthetic report</button>
        </>}
      />
      {!loading && !error && recentSessions.length === 0 && (
        <EmptyState
          title="No documents yet"
          body="Upload a lab report or explore MediGuide with synthetic data."
        >
          <button className="forest-button" type="button" onClick={onUpload}>Upload document</button>
          <button className="quiet-button" type="button" onClick={onLoadSample}>Try synthetic report</button>
        </EmptyState>
      )}
      {!loading && <div className={dragging ? "upload-zone is-dragging" : "upload-zone"} onDrop={onDrop} onDragEnter={(event) => { event.preventDefault(); onDragEnter(); }} onDragOver={(event) => event.preventDefault()} onDragLeave={onDragLeave}>
        <span className="upload-art"><FileText size={25} /><span><ImageIcon size={14} /></span></span>
        <strong>Drop a PDF or image here</strong>
        <span>Lab reports · For MRI / X-ray / CT reports use Imaging</span>
        <div className="upload-actions">
          <button className="forest-button" type="button" onClick={onUpload}>Choose file <Paperclip size={16} /></button>
          <button className="quiet-button" type="button" onClick={onLoadSample}>Try synthetic report</button>
        </div>
      </div>}
      {demoGuide && <p className="demo-guide-banner">{demoGuide}</p>}
      {(loading || processStage) && <ProcessingChecklist activeStage={processStage || mapStatusToProcessStage("", loading)} failed={processFailed} waitingMessage={processRetry ? "Document processing is starting up." : undefined} attempt={processRetry?.attempt} maxAttempts={processRetry?.max} />}
      {loading && !processStage && <div className="processing large"><Sparkles size={18} /> {loading}<i /><i /><i /></div>}
      {error && <ServiceError title={uploadErrorTitle} message={uploadErrorMessage} onRetry={onRetry} onSystem={onSystem} />}
      {errorKind === "extract" && error && <div className="explain-actions"><button type="button" className="quiet-button" onClick={onRemove}>Remove document</button></div>}
      {!loading && recentSessions.length > 0 && <div className="document-list">
        <p className="eyebrow">RECENT DOCUMENTS</p>
        <Table>
          <thead>
            <tr>
              <th>Document</th>
              <th>Pages</th>
              <th>Extracted</th>
              <th>Verification</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {recentSessions.map((session) => (
              <tr key={session.document_id}>
                <td>
                  <button type="button" className="document-table-name" onClick={() => onOpenSession(session.document_id)}>
                    <FileText size={15} />
                    <strong>{session.filename}</strong>
                  </button>
                </td>
                <td>{session.page_count || "—"}</td>
                <td>{session.field_count}</td>
                <td>{session.confirmed ? "Verified" : "Not yet verified"}</td>
                <td><StatusChip {...documentStatusChip(session.status, session.confirmed)} /></td>
                <td><button type="button" className="quiet-button" onClick={() => onOpenSession(session.document_id)}>Open</button></td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>}
    </div>;
  }

  const activePreview = docState.pages.find((page) => page.page_number === docSelectedPage) || docState.pages[0];
  // Pages that were hard to read, for one plain-language warning above review.
  const hardPages = docState.pages.filter((page) => page.quality === "poor" || page.quality === "unreadable" || page.text_source === "vision" || (page.quality_notes || []).some((note) => /Low resolution|Blurry|Low contrast/.test(note)));
  // Nothing was extracted: there is nothing to review or confirm, so the page
  // explains why once and offers ways forward instead of a confirm step.
  const nothingFound = !docConfirmed && !loading && !processStage && docFields.length === 0;
  const pageNotes = Array.from(new Set(docState.pages.flatMap((page) => page.quality_notes || [])));

  if ((loading || processStage) && !docFields.length) {
    return <div className="workflow-view doc-intel-view">
      <PageHero
        eyebrow="Documents"
        title={docState.filename}
        lead="Processing your document while keeping the original file available."
      />
      <ProcessingChecklist activeStage={processStage || mapStatusToProcessStage(docState.status, loading)} failed={processFailed} waitingMessage={processRetry ? "Document processing is starting up." : undefined} attempt={processRetry?.attempt} maxAttempts={processRetry?.max} />
      {error && <ServiceError title={uploadErrorTitle} message={uploadErrorMessage} onRetry={onRetry} onSystem={onSystem} />}
      {error && (
        <div className="explain-actions">
          <button type="button" className="quiet-button" onClick={onRetry}>Retry processing</button>
          <button type="button" className="quiet-button" onClick={onRemove}>Remove document</button>
          {onOpenImaging ? (
            <button type="button" className="forest-button" onClick={onOpenImaging}>
              Open Imaging instead
            </button>
          ) : null}
        </div>
      )}
      {error && /AI service|did not respond|timeout|vision service|not available|Imaging instead|lab document|radiology/i.test(error) ? (
        <p className="imaging-boundary" style={{ marginTop: 12 }}>
          Your original file is still available. Phone photos of radiology reports belong in{" "}
          <strong>Imaging</strong> (MRI / X-ray / CT report text), not Documents lab extraction.
          If Imaging already extracted this report, continue verification there — retrying Documents
          will not improve a radiology photo.
        </p>
      ) : null}
    </div>;
  }

  return <div className="workflow-view doc-intel-view">
    <PageHero
      eyebrow="Document review"
      title={docState.filename}
      lead={`${docState.page_count} page${docState.page_count === 1 ? "" : "s"} · ${docConfirmed ? "These values are saved to your records and timeline." : "Check each value against the original page, then confirm."}`}
      meta={docConfirmed ? <span><ShieldCheck size={14} /> Confirmed by you</span> : <span><ShieldCheck size={14} /> Review required</span>}
      actions={<>
        {docFields.length > 0 && <button className="quiet-button" onClick={onExportFields}><Clipboard size={14} /> Export fields</button>}
        <button className="quiet-button" onClick={onReset}><Trash2 size={14} /> Delete document</button>
      </>}
    />

    {!docConfirmed && (docState.extraction_version ?? 1) < CURRENT_EXTRACTION_VERSION && (!docState.content_type || docState.content_type.includes("pdf")) && (
      <div className="reread-banner" role="status">
        <div>
          <strong>Read with an older extraction method</strong>
          <p>Some names, values or units on this document may be mapped incorrectly. Nothing from it is in your records yet. Re-read it with the current method, then review again.</p>
        </div>
        <button type="button" className="forest-button" disabled={Boolean(loading)} onClick={onReread}><RefreshCw size={15} /> Re-read document</button>
      </div>
    )}

    {!docConfirmed && docState.duplicate_of && (
      <div className="duplicate-banner" role="status">
        <div>
          <strong>You already confirmed this file</strong>
          <p>It is identical to <em>{docState.duplicate_of.filename}</em>. Confirming it again would add the same results to your records twice.</p>
        </div>
        <button type="button" className="quiet-button" onClick={() => onOpenSession(docState.duplicate_of!.document_id)}>Open confirmed copy</button>
      </div>
    )}

    {!docConfirmed && !nothingFound && hardPages.length > 0 && (
      <div className="scan-quality-banner" role="status">
        <strong>{hardPages.length === 1 ? `Page ${hardPages[0].page_number} was hard to read` : `${hardPages.length} pages were hard to read`}</strong>
        <ul>
          {hardPages.map((page) => (
            <li key={page.page_number}>Page {page.page_number}: {(page.quality_notes || []).join(" · ") || "Low reading quality"}</li>
          ))}
        </ul>
        <p>Check each value carefully against the page. If anything is unclear, upload a sharper, well-lit scan or photo.</p>
      </div>
    )}

    {sourceBreadcrumb && (
      <div className="source-breadcrumb" aria-label="Source navigation">
        <span>{sourceBreadcrumb}</span>
        <button type="button" className="quiet-button" onClick={() => { onClearBreadcrumb(); onBackToSource(); }}>← Back</button>
      </div>
    )}

    {error && (
      <div className="doc-error-recovery">
        <ServiceError title={uploadErrorTitle} message={uploadErrorMessage} onRetry={onRetry} onSystem={onSystem} />
        <div className="explain-actions">
          <button type="button" className="quiet-button" onClick={onRetry}>Retry processing</button>
          <button type="button" className="quiet-button" onClick={onRemove}>Remove document</button>
        </div>
      </div>
    )}
    {(loading || processStage) && <ProcessingChecklist activeStage={processStage || mapStatusToProcessStage(docState.status, loading)} failed={processFailed} waitingMessage={processRetry ? "Document processing is starting up." : undefined} attempt={processRetry?.attempt} maxAttempts={processRetry?.max} />}
    {demoGuide && !nothingFound && <p className="demo-guide-banner">{docConfirmed ? "Step 1 of 4 complete — your values are confirmed. Next: see them in Labs." : demoGuide}{docConfirmed ? <>{" "}<button type="button" className="quiet-button" onClick={onOpenLabsFromDemo}>Open Labs</button></> : null}</p>}
    {labsHint && <div className="labs-persist-hint-row">
      <p className="labs-persist-hint"><FlaskConical size={14} /> {labsHint}</p>
      {confirmedLabCodes.length > 0 && <button type="button" className="quiet-button" onClick={onOpenLabs}><TrendingUp size={14} /> View in Labs</button>}
    </div>}

    {activePreview?.text_source && !nothingFound && (
      <p className={`page-read-info quality-${activePreview.quality || "none"}`}>
        {pageReadLabel(activePreview)}
      </p>
    )}

    <DocumentReview
      apiUrl={apiUrl}
      docState={docState}
      docFields={docFields}
      docConfirmed={docConfirmed}
      docSelectedPage={docSelectedPage}
      setDocSelectedPage={setDocSelectedPage}
      highlightedFieldId={highlightedFieldId}
      setHighlightedFieldId={setHighlightedFieldId}
      fieldReviewState={fieldReviewState}
      draftStatus={draftStatus}
      previewZoom={previewZoom}
      setPreviewZoom={setPreviewZoom}
      docReviewChecked={docReviewChecked}
      setDocReviewChecked={setDocReviewChecked}
      loading={loading}
      onSaveCorrection={onFieldChange}
      onDecide={onDecide}
      onUndo={onUndo}
      onConfirm={onConfirm}
      emptyFields={nothingFound ? (
        <EmptyState
          title="No lab results could be read from this document"
          body={`${pageNotes.length ? `${pageNotes.join(" · ")}. ` : ""}Nothing from it has been added to your records. Upload a sharper, well-lit scan or the original PDF and try again. If this is an MRI, X-ray or CT report, use Imaging instead.`}
        >
          <button type="button" className="forest-button" onClick={onUpload}><Paperclip size={15} /> Upload a clearer copy</button>
          {onOpenImaging ? <button type="button" className="quiet-button" onClick={onOpenImaging}>Open Imaging</button> : null}
          <button type="button" className="quiet-button" onClick={onReset}><Trash2 size={14} /> Delete document</button>
        </EmptyState>
      ) : undefined}
      afterFields={<>
        {docConfirmed && !docExplain && !onExplain && <div className="explain-actions">
          <button className="quiet-button" type="button" onClick={onOpenLabs}><FlaskConical size={15} /> Open Labs</button>
          <button className="quiet-button" type="button" onClick={onPrepareVisit}><Stethoscope size={15} /> Prepare visit questions</button>
        </div>}
        {docConfirmed && !docExplain && onExplain && <div className="explain-gate">
          <label className="explain-question">Ask a question about this document (optional)<textarea rows={3} value={docQuestion} onChange={(event) => setDocQuestion(event.target.value)} placeholder="Explain the confirmed information in plain language and suggest questions for a qualified healthcare professional." /></label>
          <div className="explain-actions">
            <button className="quiet-button" type="button" onClick={onOpenLabs}><FlaskConical size={15} /> Open Labs</button>
            <button className="quiet-button" type="button" onClick={onPrepareVisit}><Stethoscope size={15} /> Prepare visit questions</button>
            {onAskAbout && <button className="quiet-button" type="button" onClick={onAskAbout}><Sparkles size={15} /> Ask about these values</button>}
            <button className="quiet-button" type="button" onClick={onSuggestQuestions}>Suggest questions</button>
            <button className="forest-button" disabled={Boolean(loading)} onClick={onExplain}>Understand this result <ArrowUpRight size={16} /></button>
          </div>
        </div>}
        {docConfirmed && docExplain && <div className="explain-actions">
          <button className="quiet-button" type="button" onClick={onOpenLabs}><FlaskConical size={15} /> Open Labs</button>
          <button className="quiet-button" type="button" onClick={onPrepareVisit}><Stethoscope size={15} /> Prepare visit questions</button>
          {onAskAbout && <button className="quiet-button" type="button" onClick={onAskAbout}><Sparkles size={15} /> Ask about these values</button>}
        </div>}
      </>}
    />

    {loading && !processStage && <div className="processing"><Sparkles size={17} /><span>{loading}</span><i /><i /><i /></div>}

    {docExplain && <DocExplainCard explain={docExplain} selectedSource={selectedSource} setSelectedSource={setSelectedSource} onJumpToPage={setDocSelectedPage} />}
  </div>;
}

function DocExplainCard({ explain, selectedSource, setSelectedSource, onJumpToPage }: { explain: DocExplain; selectedSource: number | null; setSelectedSource: (value: number | null) => void; onJumpToPage: (page: number) => void }) {
  const lines = explain.answer_markdown.split("\n");
  const renderPart = (part: string, key: string) => {
    const pageMatch = /^\[D(\d+)\]$/.exec(part);
    if (pageMatch) {
      const page = Number(pageMatch[1]);
      return <button className="doc-citation" onClick={() => onJumpToPage(page)} key={key}>[D{page}]</button>;
    }
    const numbers = /^\[\d+(?:,\s*\d+)*\]$/.test(part) ? part.match(/\d+/g) : null;
    if (!numbers) return part.replace(/^#+\s*/, "");
    return numbers.map((num, index) => (
      <button className={selectedSource === Number(num) ? "citation selected" : "citation"} onClick={() => setSelectedSource(Number(num))} key={`${key}-${index}`}>[{num}]</button>
    ));
  };
  return <article className="answer-document doc-explain-card">
    <div className="answer-kicker"><span><Sparkles size={14} /> MEDIGUIDE</span><small>Educational context</small></div>
    <p className="eyebrow explain-provenance-label">GROUNDED EXPLANATION</p>
    <div className="explain-split-note">
      <strong>What your document says</strong> stays separate from <strong>general educational information</strong>.
    </div>
    <div className="answer-content">
      {lines.map((line, index) => {
        const heading = line.startsWith("#");
        const parts = line.split(/(\[D\d+\]|\[\d+(?:,\s*\d+)*\])/g);
        return <p className={heading ? "answer-heading" : ""} key={index}>{parts.map((part, partIndex) => renderPart(part, `${index}-${partIndex}`))}</p>;
      })}
    </div>
    {explain.sources.length > 0 && (
      <div className="explain-provenance-list">
        <p className="eyebrow">SOURCES</p>
        <ul>
          {explain.sources.map((source) => (
            <li key={source.citation_number}>
              <strong>[{source.citation_number}]</strong> {source.publisher} — {source.title}
            </li>
          ))}
        </ul>
      </div>
    )}
    {explain.limitations.length > 0 && <div className="doc-limitations"><p className="eyebrow">LIMITATIONS</p><ul>{explain.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
    <p className="answer-safety-note"><ShieldCheck size={13} /> General educational information, not a diagnosis or personalized treatment recommendation.</p>
  </article>;
}

export function Medication({
  apiUrl, medState, medConfirmed, onStateChange,
  medInfo, medQuestion, setMedQuestion, medTypedText, setMedTypedText,
  selectedSource, setSelectedSource,
  dragging, onUpload, onDrop, onDragEnter, onDragLeave, onGetInfo, onSubmitTyped, onSample, onPrepareVisit, onReset,
  loading, error,
}: {
  apiUrl: string;
  medState: MedState | null;
  medConfirmed: boolean;
  onStateChange: (state: MedState) => void;
  medInfo: MedInfo | null;
  medQuestion: string;
  setMedQuestion: (value: string) => void;
  medTypedText: string;
  setMedTypedText: (value: string) => void;
  selectedSource: number | null;
  setSelectedSource: (value: number | null) => void;
  dragging: boolean;
  onUpload: () => void;
  onDrop: (event: DragEvent<HTMLDivElement>) => void;
  onDragEnter: () => void;
  onDragLeave: () => void;
  onGetInfo: () => void;
  onSubmitTyped: () => void;
  onSample: () => void;
  onPrepareVisit: () => void;
  onReset: () => void;
  loading: string;
  error: string;
}) {
  if (!medState) {
    return <div className="workflow-view">
      <PageHero
        eyebrow="Medication workspace"
        title="Understand a"
        accent="medication label."
        lead="Upload a photo of a label, or type what is printed on it — review the extracted name, strength, and instructions before MediGuide adds educational information."
        meta={<span><ShieldCheck size={14} /> Human review first</span>}
      />
      {!loading && <div className={dragging ? "upload-zone is-dragging" : "upload-zone"} onDrop={onDrop} onDragEnter={(event) => { event.preventDefault(); onDragEnter(); }} onDragOver={(event) => event.preventDefault()} onDragLeave={onDragLeave}>
        <span className="upload-art"><Pill size={25} /><span><ImageIcon size={14} /></span></span>
        <strong>Upload a medication label</strong>
        <span>Drop a photo or PDF here, or choose a file</span>
        <small>PDF, PNG, JPG, WEBP · Temporary session file</small>
        <div className="upload-actions">
          <button className="forest-button" onClick={onUpload}>Choose file <Paperclip size={16} /></button>
          <button className="quiet-button" type="button" onClick={onSample}>Try sample Amoxicillin label</button>
        </div>
      </div>}
      {!loading && <div className="med-type-alt">
        <p className="eyebrow">OR TYPE THE LABEL</p>
        <textarea rows={3} value={medTypedText} onChange={(event) => setMedTypedText(event.target.value)} placeholder="e.g. Amoxicillin 500 mg capsules — Take 1 capsule by mouth three times daily for 10 days" />
        <button className="quiet-button" disabled={!medTypedText.trim()} onClick={onSubmitTyped}>Extract from typed text <ArrowUpRight size={16} /></button>
      </div>}
      {loading && <div className="processing large"><Sparkles size={18} /> {loading}<i /><i /><i /></div>}
      {error && <div className="service-error"><Activity size={19} /><div><strong>{error}</strong><p>Nothing has been added.</p></div></div>}
      <MedicationRecords apiUrl={apiUrl} refreshKey="landing" />
    </div>;
  }

  return <div className="workflow-view doc-intel-view">
    <PageHero
      eyebrow="Medication workspace"
      title={medState.filename || (medState.source === "typed" ? "Your medication label" : "Medication label")}
      lead={medConfirmed ? "Confirmed by you" : "Review each detail before confirming"}
      actions={<button className="quiet-button" onClick={onReset}><RefreshCw size={14} /> Start over</button>}
    />

    {error && <div className="service-error"><Activity size={19} /><div><strong>{error}</strong><p>Try again below.</p></div></div>}

    <MedicationReview apiUrl={apiUrl} medState={medState} onStateChange={onStateChange} />

    {medConfirmed && <section className="med-education" aria-labelledby="med-education-title">
      <p className="eyebrow" id="med-education-title">GENERAL INFORMATION · SEPARATE FROM YOUR LABEL</p>
      <p className="med-education-note">
        Educational information about this kind of medicine, from approved sources. It never changes the directions on your label,
        and it is not advice to start, stop or change a dose.
      </p>
      {!medInfo && <div className="explain-gate">
        <label className="explain-question">Ask a question about this medication (optional)<textarea rows={2} value={medQuestion} onChange={(event) => setMedQuestion(event.target.value)} placeholder="What should I know about this medication?" /></label>
        <div className="explain-actions">
          <button className="quiet-button" type="button" onClick={onPrepareVisit}><Stethoscope size={15} /> Add to visit prep</button>
          <button className="forest-button" disabled={Boolean(loading)} onClick={onGetInfo}>Get educational information <ArrowUpRight size={16} /></button>
        </div>
      </div>}
      {medInfo && <div className="explain-actions">
        <button className="quiet-button" type="button" onClick={onPrepareVisit}><Stethoscope size={15} /> Add to visit prep</button>
      </div>}
    </section>}

    <MedicationRecords apiUrl={apiUrl} refreshKey={(medState.entries || []).map((entry) => entry.decision).join(",")} />

    {loading && <div className="processing"><Sparkles size={17} /><span>{loading}</span><i /><i /><i /></div>}

    {medInfo && <MedInfoCard info={medInfo} selectedSource={selectedSource} setSelectedSource={setSelectedSource} />}
  </div>;
}

function MedInfoCard({ info, selectedSource, setSelectedSource }: { info: MedInfo; selectedSource: number | null; setSelectedSource: (value: number | null) => void }) {
  const lines = info.answer_markdown.split("\n");
  const renderPart = (part: string, key: string) => {
    const numbers = /^\[\d+(?:,\s*\d+)*\]$/.test(part) ? part.match(/\d+/g) : null;
    if (!numbers) return part.replace(/^#+\s*/, "");
    return numbers.map((num, index) => (
      <button className={selectedSource === Number(num) ? "citation selected" : "citation"} onClick={() => setSelectedSource(Number(num))} key={`${key}-${index}`}>[{num}]</button>
    ));
  };
  return <article className="answer-document doc-explain-card">
    <div className="answer-kicker"><span><Sparkles size={14} /> MEDIGUIDE</span><small>Medication information</small></div>
    <div className="answer-content">
      {lines.map((line, index) => {
        const heading = line.startsWith("#");
        const parts = line.split(/(\[\d+(?:,\s*\d+)*\])/g);
        return <p className={heading ? "answer-heading" : ""} key={index}>{parts.map((part, partIndex) => renderPart(part, `${index}-${partIndex}`))}</p>;
      })}
    </div>
    {info.limitations.length > 0 && <div className="doc-limitations"><p className="eyebrow">LIMITATIONS</p><ul>{info.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
    <p className="answer-safety-note"><ShieldCheck size={13} /> General educational information, not personalized dosing guidance. Confirm with a pharmacist or clinician.</p>
  </article>;
}

function buildVisitSummaryText(fields: Record<string, string>, includeLabs: boolean, includeMeds: boolean, labPoints: LabPoint[], medFields: MedField[]) {
  const lines: string[] = ["Patient-Provided Visit Preparation Summary", ""];
  const order = ["Main concern", "Symptoms", "Onset", "Duration", "Frequency", "Severity", "Triggers", "Relieving factors", "Medications as entered", "Questions for clinician"];
  for (const key of order) {
    const value = (fields[key] || "").trim();
    if (value) lines.push(`${key}: ${value}`, "");
  }
  if (includeLabs && labPoints.length) {
    lines.push("Verified labs summary (patient-confirmed):");
    for (const point of labPoints.slice(0, 8)) {
      lines.push(`- ${point.test_name}: ${point.value_text} ${point.unit}${(point.date || point.report_date) ? ` (${point.date || point.report_date})` : ""}`);
    }
    lines.push("");
  }
  if (includeMeds) {
    const medNotes = medFields.filter((field) => field.value.trim()).map((field) => `${field.label}: ${field.value}`).join("; ");
    const fromVisit = (fields["Medications as entered"] || "").trim();
    if (medNotes || fromVisit) {
      lines.push("Medication notes:", medNotes || fromVisit, "");
    }
  }
  lines.push("This is patient-provided preparation material for discussion with a clinician — not a clinical note or diagnosis.");
  return lines.join("\n").trim();
}

export function Visit({ fields, setFields, step, setStep, labPoints, medFields, onGenerate }: { fields: Record<string, string>; setFields: (value: Record<string, string>) => void; step: number; setStep: (value: number) => void; labPoints: LabPoint[]; medFields: MedField[]; onGenerate?: () => void }) {
  const [includeLabs, setIncludeLabs] = useState(true);
  const [includeMeds, setIncludeMeds] = useState(true);
  const [summary, setSummary] = useState("");

  useEffect(() => {
    // Regenerates the editable draft when entering step 4 or its inputs
    // change; user edits to the textarea itself are not overwritten otherwise.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (step === 4) setSummary(buildVisitSummaryText(fields, includeLabs, includeMeds, labPoints, medFields));
  }, [step, fields, includeLabs, includeMeds, labPoints, medFields]);

  const setField = (key: string, value: string) => setFields({ ...fields, [key]: value });
  const steps = ["Concern", "Timeline", "Questions", "Summary"];

  return <div className="workflow-view visit-wizard">
    <PageHero
      eyebrow="Visit preparation"
     
      title="Make the visit"
      accent="count."
      lead="Organize patient-provided information into a clear visit preparation summary."
    />
    <div className="visit-wizard-steps" aria-label="Visit preparation steps">
      <div className="visit-step-pills">
        {steps.map((label, index) => (
          <button type="button" key={label} className={step === index + 1 ? "visit-step-pill active" : "visit-step-pill"} onClick={() => setStep(index + 1)}>
            <span>{index + 1}</span>{label}
          </button>
        ))}
      </div>
    </div>

    {step === 1 && <div className="visit-form">
      <label>Main concern<textarea rows={3} value={fields["Main concern"] || ""} onChange={(event) => setField("Main concern", event.target.value)} placeholder="What do you most want to discuss?" /></label>
      <label>Symptoms<textarea rows={3} value={fields.Symptoms || ""} onChange={(event) => setField("Symptoms", event.target.value)} placeholder="Describe symptoms in your own words..." /></label>
    </div>}

    {step === 2 && <div className="visit-form">
      {(["Onset", "Duration", "Frequency", "Severity", "Triggers", "Relieving factors", "Medications as entered"] as const).map((name) => (
        <label key={name}>{name}<textarea rows={2} value={fields[name] || ""} onChange={(event) => setField(name, event.target.value)} placeholder={`Add ${name.toLowerCase()}...`} /></label>
      ))}
    </div>}

    {step === 3 && <div className="visit-form">
      <label>Questions for clinician<textarea rows={5} value={fields["Questions for clinician"] || ""} onChange={(event) => setField("Questions for clinician", event.target.value)} placeholder="List questions you want to ask..." /></label>
      <button type="button" className="quiet-button" onClick={() => setField("Questions for clinician", suggestClinicianQuestions([], medFields, labPoints))}>Suggest from labs &amp; medications</button>
    </div>}

    {step === 4 && <div className="visit-form visit-summary-step">
      <label>Patient-Provided Visit Preparation Summary<textarea rows={12} value={summary} onChange={(event) => setSummary(event.target.value)} /></label>
      <label className="confirm"><input type="checkbox" checked={includeLabs} onChange={(event) => setIncludeLabs(event.target.checked)} /> Include verified labs summary</label>
      <label className="confirm"><input type="checkbox" checked={includeMeds} onChange={(event) => setIncludeMeds(event.target.checked)} /> Include medication notes</label>
      <div className="visit-summary-actions">
        <button type="button" className="quiet-button" onClick={() => void navigator.clipboard?.writeText(summary)}><Clipboard size={14} /> Copy</button>
        <button type="button" className="quiet-button" onClick={() => window.print()}>Print</button>
        <button type="button" className="quiet-button" onClick={() => downloadTextFile("mediguide-visit-prep.txt", summary)}><ArrowUpRight size={14} /> Download summary</button>
        {onGenerate && <button type="button" className="forest-button" onClick={onGenerate}>Continue in conversation <ArrowUpRight size={16} /></button>}
      </div>
    </div>}

    <p className="patient-note"><ShieldCheck size={16} /> Patient-provided information — not a clinical note or diagnosis.</p>
    <div className="visit-nav">
      <button type="button" className="quiet-button" disabled={step <= 1} onClick={() => setStep(step - 1)}>Back</button>
      {step < 4 ? <button type="button" className="forest-button" onClick={() => setStep(step + 1)}>Next</button> : null}
    </div>
  </div>;
}

export function DemoMode({ onSyntheticPipeline, onSampleMedication, onSampleVoice, onSampleVisit }: { onSyntheticPipeline: () => void; onSampleMedication: () => void; onSampleVoice: () => void; onSampleVisit: () => void }) {
  return <div className="workflow-view">
    <PageHero
      eyebrow="Demo mode"
     
      title="Try with"
      accent="synthetic data."
      lead="One click loads a three-date synthetic lab report (January, April, August). No personal medical information is required."
      actions={<>
        <button type="button" className="forest-button demo-hero-cta" onClick={onSyntheticPipeline}>
          <PlayCircle size={18} /> Try with synthetic data
        </button>
        <p className="demo-pipeline-caption">Walkthrough: extraction → verification → Labs → explanation → source-page drill-down</p>
      </>}
    />
    <div className="demo-grid demo-secondary-grid">
      <button type="button" className="demo-card" onClick={onSampleMedication}>
        <span className="quick-icon"><Pill size={18} /></span>
        <strong>Sample medication label</strong>
        <small>Supporting workflow — Amoxicillin educational review.</small>
      </button>
      <button type="button" className="demo-card" onClick={onSampleVoice}>
        <span className="quick-icon"><Mic size={18} /></span>
        <strong>Sample Ask MediGuide question</strong>
        <small>Supporting conversation with a synthetic CBC question.</small>
      </button>
      <button type="button" className="demo-card" onClick={onSampleVisit}>
        <span className="quick-icon"><Stethoscope size={18} /></span>
        <strong>Sample visit preparation</strong>
        <small>Supporting appointment notes and clinician questions.</small>
      </button>
    </div>
  </div>;
}

export function EvaluationDashboard() {
  const [unlocked, setUnlocked] = useState(false);
  if (!unlocked) {
    return <div className="workflow-view">
      <PageHero eyebrow="Evaluation" title="Engineering evaluation" lead="Synthetic test metrics for portfolio review. Protected from casual browsing." />
      <div className="eval-gate">
        <Lock size={18} />
        <p>Unlock to view synthetic evaluation results.</p>
        <button type="button" className="forest-button" onClick={() => setUnlocked(true)}>Unlock for portfolio demo</button>
      </div>
    </div>;
  }
  return <div className="workflow-view">
    <div className="eval-banner"><Lock size={14} /> Engineering evaluation (synthetic tests — no patient data)</div>
    <PageHero eyebrow="Evaluation" title="Safety & quality metrics" lead="Results from synthetic regression suites used in engineering review." />
    <table className="eval-table">
      <thead><tr><th>Check</th><th>Result</th><th>Metric</th></tr></thead>
      <tbody>
        {EVALUATION_METRICS.map((row) => {
          const passed = row.passed == null || row.total == null ? null : row.passed === row.total;
          return <tr key={row.name}>
            <td>{row.name}</td>
            <td>{passed == null ? "—" : passed ? "Pass" : "Fail"}</td>
            <td>{row.metric}{row.passed != null && row.total != null ? ` (${row.passed}/${row.total})` : ""}</td>
          </tr>;
        })}
      </tbody>
    </table>
  </div>;
}

function reportFlagLabel(status?: string) {
  if (status === "flagged_high_on_report") return "Flagged high on this report";
  if (status === "flagged_low_on_report") return "Flagged low on this report";
  return "";
}

function confidenceLabel(confidence?: string) {
  if (confidence === "clearly_visible") return "Clearly visible";
  if (confidence === "needs_review") return "Needs review";
  if (confidence === "could_not_read") return "Could not read";
  return "";
}

function formatCollectionDate(value?: string | null) {
  if (!value) return "Not listed";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function pointDate(point: LabPoint) {
  return point.date || point.collection_date || point.report_date || null;
}

/** "Collected" only when the confirmed date really is a collection date. */
function dateKindLabel(point: LabPoint) {
  if (!pointDate(point)) return "No date on report";
  if (point.date_source === "collection") return "Collected";
  if (point.date_source === "report") return "Report date";
  return "Date on report";
}

function notPlottedNote(point: LabPoint, seriesUnit: string) {
  switch (point.not_plotted_reason) {
    case "duplicate": return `Same result as in ${point.duplicate_document_name || "another report"}, so it is shown once on the chart`;
    case "qualified_value": return "Printed as a limit, not an exact number, so it is not drawn on the chart";
    case "not_numeric": return "Not a number, so it is not drawn on the chart";
    case "no_date": return "No confirmed date, so it can't be placed on the chart";
    case "different_unit": return `Reported in ${point.unit || "a different unit"}${seriesUnit ? `, not ${seriesUnit}` : ""}. Not converted or drawn on the chart`;
    default: return "";
  }
}

export function LabTimeline({
  tests, selectedCode, onSelectCode, points, selectedPoint, onSelectPoint, onInspectDocument, onExport, onAddToVisit, onAskAbout, onRequestDeleteObservation, onOpenDocuments,
}: {
  tests: LabTest[];
  selectedCode: string;
  onSelectCode: (code: string) => void;
  points: LabPoint[];
  selectedPoint: LabPoint | null;
  onSelectPoint: (point: LabPoint | null) => void;
  onInspectDocument: (documentId: string, pageNumber: number, fieldId?: string) => void;
  onExport: () => void;
  onAddToVisit: () => void;
  onAskAbout?: () => void;
  onRequestDeleteObservation: (observationId: string) => void;
  onOpenDocuments: () => void;
}) {
  const activeTest = (tests.find((test) => test.test_code === selectedCode)?.display_name) || selectedCode;
  const selectedDate = selectedPoint ? pointDate(selectedPoint) : null;
  const selectedPage = selectedPoint?.source_page || selectedPoint?.page_number || 1;
  const selectedReference = selectedPoint?.reference_range || selectedPoint?.reference_text;
  const selectedVerification = selectedPoint?.verification_status || selectedPoint?.verification_state;
  const reportFlag = reportFlagLabel(selectedPoint?.range_status);
  const uniqueDocuments = new Set(points.map((point) => point.document_id)).size;
  const extractionConfidence = confidenceLabel(selectedPoint?.confidence);
  // Latest = the most recent dated result that isn't a repeat of another.
  const dated = points.filter((point) => pointDate(point) && !point.duplicate_of);
  const latest = dated.length ? dated[dated.length - 1] : points.length ? points[points.length - 1] : null;
  const chartPoints = points.filter(isPlottable);
  const seriesUnit = chartPoints.length ? chartPoints[chartPoints.length - 1].unit : "";
  const offChart = points.filter((point) => !isPlottable(point));
  const duplicateCount = points.filter((point) => point.duplicate_of).length;
  const otherUnits = Array.from(new Set(points.filter((point) => point.not_plotted_reason === "different_unit").map((point) => point.unit || "no unit")));
  const conflictDates = Array.from(new Set(points.filter((point) => point.conflicting_values?.length).map((point) => formatCollectionDate(pointDate(point)))));
  const testOptions = tests.length ? tests : [{ test_code: "hemoglobin_a1c", display_name: "Hemoglobin A1C", observation_count: 0, has_data: false }];
  const withData = testOptions.filter((test) => test.has_data);
  const withoutData = testOptions.filter((test) => !test.has_data);

  return <div className="workflow-view lab-timeline-view">
    <PageHero
      eyebrow="Lab timeline"
     
      title="Labs"
      lead="Explore verified measurements across reports."
      actions={<>
        <label className="timeline-control">
          <span className="sr-only">Test selector</span>
          <select value={selectedCode} onChange={(event) => onSelectCode(event.target.value)} aria-label="Test selector">
            {!testOptions.some((test) => test.test_code === selectedCode) && <option value={selectedCode}>{activeTest}</option>}
            {withData.length > 0 && <optgroup label="Your results">
              {withData.map((test) => <option key={test.test_code} value={test.test_code}>{test.display_name} ({test.observation_count})</option>)}
            </optgroup>}
            {withoutData.length > 0 && <optgroup label="No results yet">
              {withoutData.map((test) => <option key={test.test_code} value={test.test_code}>{test.display_name}</option>)}
            </optgroup>}
          </select>
        </label>
        {onAskAbout && <button type="button" className="quiet-button" onClick={onAskAbout} disabled={!points.length}><Sparkles size={14} /> Understand this result</button>}
        <button type="button" className="quiet-button" onClick={onAddToVisit}><Stethoscope size={14} /> Add to visit prep</button>
        <button type="button" className="quiet-button" onClick={onExport} disabled={!points.length}><Clipboard size={14} /> Export CSV</button>
        {!points.length && <p className="page-hero-note">{onAskAbout ? "Understanding and export become" : "Export becomes"} available once this test has verified results.</p>}
      </>}
    />

    {latest && (
      <div className="latest-result-card">
        <p className="panel-kicker">Latest verified result · {activeTest}</p>
        <p className="lab-result-value">{latest.value_text} {latest.unit}</p>
        <p className="lab-result-date">{pointDate(latest) ? `${dateKindLabel(latest)} ${formatCollectionDate(pointDate(latest))}` : "No date on report"}</p>
        {latest.original_name && latest.original_name !== latest.test_name ? <p className="latest-ref">Printed on the report as “{latest.original_name}”</p> : null}
        {reportFlagLabel(latest.range_status) ? <p className="lab-range-flag">{reportFlagLabel(latest.range_status)}</p> : null}
        {(latest.reference_range || latest.reference_text) ? <p className="latest-ref">Printed reference range: {latest.reference_range || latest.reference_text}</p> : null}
      </div>
    )}

    <div className="lab-chart-panel">
      {chartPoints.length ? (
        <LabTrendChart
          points={points}
          selectedId={selectedPoint?.observation_id}
          onSelect={onSelectPoint}
          formatDate={formatCollectionDate}
          testName={activeTest}
        />
      ) : points.length ? (
        <p className="lab-chart-empty">None of these results can be drawn on a chart (see the notes in the table), so they are listed below.</p>
      ) : (
        <EmptyState
          title="No verified measurements yet"
          body="Verified measurements will appear here after document review."
        >
          <button type="button" className="forest-button" onClick={onOpenDocuments}>Review documents</button>
        </EmptyState>
      )}
    </div>
    {points.length > 0 && <p className="lab-timeline-summary">{points.length} verified measurement{points.length === 1 ? "" : "s"} · {uniqueDocuments} source report{uniqueDocuments === 1 ? "" : "s"}{chartPoints.length === 1 ? " · one result, so no trend is shown" : ""}</p>}
    {(offChart.length > 0 || conflictDates.length > 0) && <ul className="lab-data-notes" aria-label="Notes about these results">
      {duplicateCount > 0 && <li>{duplicateCount} result{duplicateCount === 1 ? " appears" : "s appear"} in more than one report with the same date and value; each is drawn once.</li>}
      {otherUnits.length > 0 && <li>Some results use {otherUnits.join(", ")} instead of {seriesUnit || "the chart's unit"}. Units are never converted, so those are listed but not drawn.</li>}
      {offChart.some((point) => point.not_plotted_reason === "qualified_value" || point.not_plotted_reason === "not_numeric") && <li>Results printed as a limit (like “&lt;0.5”) or as text are listed but not drawn.</li>}
      {offChart.some((point) => point.not_plotted_reason === "no_date") && <li>Results without a confirmed date are listed last and not drawn. Missing dates aren&apos;t filled in.</li>}
      {conflictDates.length > 0 && <li>Different values were confirmed for the same date ({conflictDates.join(", ")}). Check the source reports.</li>}
    </ul>}
    {points.length > 0 && <table className="lab-table">
      <caption className="sr-only">{activeTest} verified measurements</caption>
      <thead><tr><th>Date</th><th>Result</th><th className="lab-col-flag">Report flag</th><th>Source</th></tr></thead>
      <tbody>
        {points.map((point) => (
          <tr
            key={point.observation_id}
            className={selectedPoint?.observation_id === point.observation_id ? "selected" : ""}
            onClick={() => onSelectPoint(point)}
            tabIndex={0}
            aria-label={`${point.value_text} ${point.unit}, ${formatCollectionDate(pointDate(point))}. Open provenance`}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelectPoint(point);
              }
            }}
          >
            <td>
              {formatCollectionDate(pointDate(point))}
              {pointDate(point) && <small className="lab-cell-note">{dateKindLabel(point)}</small>}
            </td>
            <td>
              <span className="mg-num">{point.value_text}</span> {point.unit}
              {point.reference_range || point.reference_text ? <small className="lab-cell-note">Printed range {point.reference_range || point.reference_text}</small> : null}
              {notPlottedNote(point, seriesUnit) && <small className="lab-cell-note is-flagged">{notPlottedNote(point, seriesUnit)}</small>}
              {point.conflicting_values?.length ? <small className="lab-cell-note is-flagged">Also confirmed for this date: {point.conflicting_values.join(", ")}</small> : null}
              {(point.source_flag || reportFlagLabel(point.range_status)) && <small className="lab-cell-note lab-flag-inline">Report flag: {point.source_flag === "H" ? "High" : point.source_flag === "L" ? "Low" : point.source_flag || reportFlagLabel(point.range_status)}</small>}
            </td>
            <td className="lab-col-flag">{point.source_flag === "H" ? "High" : point.source_flag === "L" ? "Low" : point.source_flag ? point.source_flag : reportFlagLabel(point.range_status) || "—"}</td>
            <td className="lab-col-source">
              {point.document_name}
              <small className="lab-cell-note">Page {point.source_page || point.page_number}</small>
            </td>
          </tr>
        ))}
      </tbody>
    </table>}
    {selectedPoint && <div className="drawer-backdrop lab-result-drawer-backdrop" onClick={() => onSelectPoint(null)}>
      <aside className="drawer lab-result-drawer" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Lab value provenance">
        <button className="drawer-close" type="button" onClick={() => onSelectPoint(null)} aria-label="Close"><X size={18} /></button>
        <p className="eyebrow">LAB VALUE PROVENANCE</p>
        <h2>{selectedPoint.test_name}</h2>
        <p className="lab-result-value">{selectedPoint.value_text} {selectedPoint.unit}</p>
        <p className="lab-result-date">{selectedDate ? `${dateKindLabel(selectedPoint)} ${formatCollectionDate(selectedDate)}` : "No date on report"}</p>
        {notPlottedNote(selectedPoint, seriesUnit) ? <p className="lab-drawer-note">{notPlottedNote(selectedPoint, seriesUnit)}</p> : null}
        {reportFlag ? <p className="lab-range-flag">{reportFlag}</p> : null}
        <p className="panel-kicker">REPORT INFORMATION</p>
        <dl>
          <div><dt>Name on report</dt><dd>{selectedPoint.original_name || selectedPoint.test_name}</dd></div>
          <div><dt>Printed reference range</dt><dd>{selectedReference || "Not listed on report"}</dd></div>
          <div><dt>Report flag</dt><dd>{selectedPoint.source_flag === "H" ? "High" : selectedPoint.source_flag === "L" ? "Low" : reportFlag || "None listed"}</dd></div>
        </dl>
        <p className="panel-kicker">VERIFICATION</p>
        <dl>
          <div><dt>Status</dt><dd>{selectedPoint.review_status === "corrected" ? "✓ Confirmed with a correction" : selectedVerification === "confirmed" || selectedVerification === "human_verified" ? "✓ Confirmed" : (selectedVerification || "Unknown")}</dd></div>
          {selectedPoint.review_status === "corrected" && selectedPoint.extracted_value != null && <div><dt>Originally read as</dt><dd>{selectedPoint.extracted_value || "Nothing (unread)"}</dd></div>}
          {selectedPoint.reviewed_at && <div><dt>Reviewed</dt><dd>{new Date(selectedPoint.reviewed_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</dd></div>}
          {extractionConfidence ? <div><dt>Extraction quality</dt><dd>{extractionConfidence} <small className="confidence-note">(extraction only — not medical correctness)</small></dd></div> : null}
        </dl>
        <p className="panel-kicker">SOURCE</p>
        <dl>
          <div><dt>Document</dt><dd>{selectedPoint.document_name}</dd></div>
          <div><dt>Page</dt><dd>{selectedPage}</dd></div>
          {selectedPoint.source_text ? <div><dt>Line on the page</dt><dd><code>{selectedPoint.source_text}</code></dd></div> : null}
        </dl>
        <div className="lab-point-actions">
          <button type="button" className="forest-button" onClick={() => onInspectDocument(selectedPoint.document_id, selectedPage, selectedPoint.field_id)}>
            <FileText size={14} /> View source page
          </button>
          {onAskAbout && <button type="button" className="quiet-button" onClick={onAskAbout}><Sparkles size={14} /> Understand this result</button>}
          <button type="button" className="quiet-button" onClick={() => onInspectDocument(selectedPoint.document_id, selectedPage)}>View document</button>
          <button type="button" className="quiet-button destructive-action" onClick={() => onRequestDeleteObservation(selectedPoint.observation_id)}>
            <Trash2 size={14} /> Delete result
          </button>
          <p className="lab-delete-note">Removes this timeline observation only. The source document stays available until you clear it separately.</p>
        </div>
      </aside>
    </div>}
  </div>;
}

export function SystemStatusView({ status, health, onRetry }: { status: SystemStatus | null; health: HealthResponse | null; onRetry: () => void }) {
  const raw = status?.components || Object.entries(health?.statuses || {}).map(([key, value]) => ({ name: friendlyHealthLabel(key, healthLabels[key] || key), key, status: value.status, detail: value.detail }));
  const byLabel = new Map<string, { name: string; key: string; status: string; detail: string }>();
  for (const component of raw) {
    // An optional integration that isn't connected (the API says "(optional)")
    // must not mark the feature it shares a label with as unavailable.
    if (component.status !== "ready" && /\(optional\)/i.test(component.detail || "")) continue;
    const name = friendlyHealthLabel(component.key, component.name);
    const existing = byLabel.get(name);
    const rank = (s: string) => (s === "ready" ? 2 : s === "degraded" ? 1 : 0);
    if (!existing || rank(component.status) < rank(existing.status)) {
      byLabel.set(name, { ...component, name });
    }
  }
  const preferred = ["Document storage", "Document processing", "Document preview", "AI-assisted extraction", "Imaging reports", "Medication labels", "Educational explanations", "Voice transcription", "Voice playback"];
  const components = preferred.map((name) => byLabel.get(name) || { name, key: name, status: "unknown", detail: "Not reported by the service" });
  const limited = components.some((component) => friendlyComponentStatus(component.status, component.detail) === "Limited" || friendlyComponentStatus(component.status, component.detail) === "Unavailable");
  return <div className="workflow-view system-status-view">
    <PageHero eyebrow="System" title="System Status" lead="Service availability for document processing and educational features. Documents and verified information remain accessible when explanations are limited." />
    {limited && <p className="system-limited-note">Some educational explanations may be temporarily unavailable. Your documents and verified information remain accessible.</p>}
    <div className="system-grid">
      {components.map((component) => {
        const label = friendlyComponentStatus(component.status, component.detail);
        return (
          <div key={component.key} className="system-card">
            <span className={label === "Available" ? "status-dot" : label === "Limited" ? "status-dot limited" : "status-dot off"} aria-hidden />
            <div>
              <strong>{component.name}</strong>
              <em className="system-health-label">{label}</em>
            </div>
          </div>
        );
      })}
    </div>
    <button className="forest-button" onClick={onRetry}><RefreshCw size={15} /> Refresh status</button>
  </div>;
}

export function Sources({ sources, library, onSelect }: { sources: Source[]; library: LibrarySource[]; onSelect: (value: number) => void }) {
  const [query, setQuery] = useState("");
  const filtered = library.filter((source) => {
    const haystack = `${source.publisher} ${source.title}`.toLowerCase();
    return haystack.includes(query.trim().toLowerCase());
  });
  if (sources.length) {
    return <div className="workflow-view"><p className="eyebrow">EXPLANATION PROVENANCE</p><h2>Cited sources.</h2><p className="workflow-lead">Plain-language statement → Citation → Approved knowledge source → Source/version</p><div className="source-list">{sources.map((source) => <button key={source.number} onClick={() => onSelect(source.number)}><span>[{source.number}]</span><div><strong>{source.publisher}</strong><b>{source.title}</b><small>{source.reviewed || "Approved source"}</small></div><ChevronRight size={17} /></button>)}</div></div>;
  }
  return <div className="workflow-view"><PageHero eyebrow="Source evidence" title="Approved" accent="sources." lead="Trusted local retrieval keeps educational explanations grounded. Lab values use a separate provenance chain back to the original report page." /><Input className="source-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search publishers or titles..." aria-label="Search approved sources" /><div className="source-list">{filtered.length ? filtered.map((source) => <a key={source.id} href={source.url || undefined} target={source.url ? "_blank" : undefined} rel={source.url ? "noreferrer" : undefined} className={source.url ? "" : "no-link"}><span><BookOpen size={15} /></span><div><strong>{source.publisher}</strong><b>{source.title}</b><small>{source.reviewed ? `Reviewed ${source.reviewed}` : "Approved source"}</small></div>{source.url && <ArrowUpRight size={16} />}</a>) : <div className="empty-panel"><BookOpen size={23} /><p>{library.length ? "No sources match that search." : "No approved sources are available yet."}</p></div>}</div></div>;
}

export function Privacy({ onClose, onClear }: { onClose: () => void; onClear: () => void }) {
  return (
    <Drawer onClose={onClose} eyebrow="PRIVACY" title="Privacy-conscious processing.">
      <p>MediGuide is an educational prototype. Your uploads and the records confirmed from them belong to your account, and no other account can open them.</p>
      <ul>
        <li><Check size={16} /> Records visible only to your account</li>
        <li><Check size={16} /> Original files kept so every value links back to its source page</li>
        <li><Check size={16} /> Permanent deletion of a document, its previews, and its lab results</li>
        <li><Check size={16} /> Educational use only</li>
        <li><Check size={16} /> No advertising profile</li>
      </ul>
      <div className="drawer-warning"><strong>Public demo mode</strong><span>Do not enter identifying health information.</span></div>
      <button className="drawer-action" onClick={onClear}><Trash2 size={16} /> Clear this screen</button>
      <button className="drawer-action secondary" onClick={() => { try { window.sessionStorage.removeItem(VISIT_STORAGE_KEY); } catch { /* ignore */ } onClear(); }}><RefreshCw size={16} /> Clear temporary session data</button>
    </Drawer>
  );
}

export function HelpDrawer({ onClose, onOpenView }: { onClose: () => void; onOpenView: (view: View) => void }) {
  return (
    <Drawer onClose={onClose} eyebrow="HELP" title="How MediGuide works.">
      <p>Primary pipeline: Documents → Verification → Labs → Grounded Explanation → Source Evidence.</p>
      <ul className="help-steps">
        <li><button type="button" onClick={() => onOpenView("demo")}><PlayCircle size={15} /> Demo Mode</button> Try with synthetic data — three-date report, no personal information.</li>
        <li><button type="button" onClick={() => onOpenView("documents")}><FileText size={15} /> Documents</button> Upload → extract → confirm values → optional explanation.</li>
        <li><button type="button" onClick={() => onOpenView("labs")}><FlaskConical size={15} /> Labs</button> Click a measurement for lab-value provenance, then View source page.</li>
        <li><button type="button" onClick={() => onOpenView("sources")}><BookOpen size={15} /> Source Evidence</button> Approved educational sources that support explanations.</li>
      </ul>
      <p className="patient-note"><ShieldCheck size={16} /> MediGuide does not autonomously diagnose conditions, prescribe treatment, or replace professional medical care.</p>
    </Drawer>
  );
}

export function SettingsDrawer({ answerDetail, setAnswerDetail, readingLevel, setReadingLevel, language, setLanguage, onClose }: { answerDetail: "Concise" | "Standard" | "Detailed"; setAnswerDetail: (value: "Concise" | "Standard" | "Detailed") => void; readingLevel: "Standard" | "Plain"; setReadingLevel: (value: "Standard" | "Plain") => void; language: string; setLanguage: (value: string) => void; onClose: () => void }) {
  return (
    <Drawer onClose={onClose} eyebrow="SETTINGS" title="Answer preferences.">
      <label>Answer detail<select value={answerDetail} onChange={(event) => setAnswerDetail(event.target.value as "Concise" | "Standard" | "Detailed")}><option>Concise</option><option>Standard</option><option>Detailed</option></select></label>
      <label>Reading level<select value={readingLevel} onChange={(event) => setReadingLevel(event.target.value as "Standard" | "Plain")}><option>Standard</option><option>Plain</option></select></label>
      <label>Preferred language<select value={language} onChange={(event) => setLanguage(event.target.value)}><option>English</option><option>Spanish</option><option>French</option></select></label>
      <p className="workflow-lead">These stay on this device only.</p>
      <button className="drawer-action" onClick={onClose}>Done</button>
    </Drawer>
  );
}

export function TranscriptReview({ text, setText, reviewed, setReviewed, onConfirm, onDiscard }: { text: string; setText: (value: string) => void; reviewed: boolean; setReviewed: (value: boolean) => void; onConfirm: () => void; onDiscard: () => void }) {
  return <div className="transcript-review">
    <p className="eyebrow">VOICE TRANSCRIPT</p>
    <strong>Review before sending.</strong>
    <textarea rows={3} value={text} onChange={(event) => setText(event.target.value)} />
    <label className="confirm"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} /> I reviewed this transcript</label>
    <div className="explain-actions">
      <button type="button" className="quiet-button" onClick={onDiscard}>Discard</button>
      <button type="button" className="forest-button" disabled={!reviewed || !text.trim()} onClick={onConfirm}>Use in question <Check size={15} /></button>
    </div>
  </div>;
}

export function Health({ health, onClose, onRetry }: { health: HealthResponse | null; onClose: () => void; onRetry: () => void }) {
  return (
    <Drawer onClose={onClose} eyebrow="SYSTEM STATUS" title={health?.status === "ok" ? "All systems ready." : "Some services need attention."} className="health-drawer">
      <p>{health ? `${health.ready} of ${health.total} services ready.` : "Checking the local AI service..."}</p>
      <div className="health-list">
        {Object.entries(health?.statuses || {}).map(([key, value]) => (
          <div key={key}>
            <span className={value.status === "ready" ? "status-dot" : "status-dot off"} />
            <strong>{healthLabels[key] || key}</strong>
            <small>{value.detail}</small>
          </div>
        ))}
      </div>
      <button className="drawer-action" onClick={onRetry}><RefreshCw size={16} /> Check again</button>
    </Drawer>
  );
}
