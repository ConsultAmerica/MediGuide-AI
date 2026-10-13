"use client";

import { DragEvent, FormEvent, KeyboardEvent, useEffect, useState } from "react";
import { Activity, ArrowUp, ArrowUpRight, BookOpen, Check, ChevronRight, Clipboard, FileText, FlaskConical, Image as ImageIcon, Lock, Mic, Paperclip, Pill, PlayCircle, Plus, RefreshCw, ShieldCheck, Sparkles, Stethoscope, Trash2, TrendingUp, Volume2, X, ZoomIn } from "lucide-react";
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
  type DocFieldStatus,
  type DocFieldConfidence,
  type DocField,
  type DocState,
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
} from "./_state/workspace-shared";
import { AuthImage } from "./_components/AuthImage";
export function Conversation({ answer, status, streaming, sources, messages, loading, error, selectedSource, setSelectedSource, onRetry, onPreset, onOpenView, onOpenDocumentPage, onUpload, onAction }: { answer: string; status: AnswerStatus; streaming: boolean; sources: Source[]; question: string; messages: Message[]; loading: string; error: string; selectedSource: number | null; setSelectedSource: (value: number | null) => void; onRetry: () => void; onPreset: (prompt: string) => void; onOpenView: (view: View) => void; onOpenDocumentPage: (page: number) => void; onUpload: () => void; onAction: (action: "copy" | "listen" | "simple" | "questions") => void }) {
  const lastQuestion = [...messages].reverse().find((item) => item.role === "user");
  const empty = !answer && !loading && !lastQuestion;
  return <div className="conversation-view">
    <div className="conversation-header">
      <div>
        <p className="eyebrow">EDUCATIONAL SUPPORT</p>
        <h2>{answer ? "Your health question, clarified." : "What can I help you understand today?"}</h2>
        {!answer && <p>Ask a health question, review a document, use your voice, or prepare for an appointment — in one workspace.</p>}
      </div>
      <div className="conversation-meta">
        <span className="response-count">{messages.filter((message) => message.role === "user").length} session {messages.filter((message) => message.role === "user").length === 1 ? "question" : "questions"}</span>
        <span className="care-mode"><ShieldCheck size={13} /> Educational support</span>
      </div>
    </div>
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
    {answer && <Answer answer={answer} status={status} streaming={streaming} sources={sources} selectedSource={selectedSource} setSelectedSource={setSelectedSource} onAction={onAction} onPreset={onPreset} onOpenView={onOpenView} onOpenDocumentPage={onOpenDocumentPage} />}
  </div>;
}

function Answer({ answer, status, streaming, sources, selectedSource, setSelectedSource, onAction, onPreset, onOpenView, onOpenDocumentPage }: { answer: string; status: AnswerStatus; streaming: boolean; sources: Source[]; selectedSource: number | null; setSelectedSource: (value: number | null) => void; onAction: (action: "copy" | "listen" | "simple" | "questions") => void; onPreset: (prompt: string) => void; onOpenView: (view: View) => void; onOpenDocumentPage: (page: number) => void }) {
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
      <div className="limited-evidence-body"><h3>{status === "withheld" ? "This answer could not be safely shown." : "Something went wrong."}</h3><p>{body}</p></div>
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
  return <article className="answer-document"><div className="answer-kicker"><span><Sparkles size={14} /> MEDIGUIDE</span><small>{streaming ? "Writing..." : "Evidence checked"}</small></div><div className="answer-content">{lines.map((line, index) => { const heading = line.startsWith("#"); const parts = line.split(/(\[D\d+\]|\[\d+(?:,\s*\d+)*\])/g); return <p className={heading ? "answer-heading" : ""} key={index}>{parts.map((part, partIndex) => renderPart(part, `${index}-${partIndex}`))}</p>; })}{streaming && <span className="streaming-cursor" aria-hidden />}</div>{!streaming && <div className="response-actions"><button onClick={() => onAction("copy")}><Clipboard size={14} /> Copy</button><button onClick={() => onAction("listen")}><Volume2 size={14} /> Listen</button><button onClick={() => onAction("simple")}><Sparkles size={14} /> Explain simply</button><button onClick={() => onAction("questions")}><Stethoscope size={14} /> Questions for clinician</button><button onClick={() => setSelectedSource(sources.length ? sources[0].number : null)}><BookOpen size={14} /> Show sources</button></div>}<p className="answer-safety-note"><ShieldCheck size={13} /> General educational information, not a diagnosis or personalized treatment recommendation.</p></article>;
}

export function Composer({ question, setQuestion, onSubmit, onKeyDown, onUpload, onVoice, recording, loading, answerDetail, setAnswerDetail, readingLevel, setReadingLevel }: { question: string; setQuestion: (value: string) => void; onSubmit: (event?: FormEvent) => void; onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void; onUpload: () => void; onVoice: () => void; recording: boolean; loading: boolean; answerDetail: "Concise" | "Standard" | "Detailed"; setAnswerDetail: (value: "Concise" | "Standard" | "Detailed") => void; readingLevel: "Standard" | "Plain"; setReadingLevel: (value: "Standard" | "Plain") => void }) {
  return <form className="composer workspace-composer" onSubmit={onSubmit} onDragOver={(event) => event.preventDefault()}>
    <div className="composer-tools">
      <button type="button" onClick={onUpload}><Paperclip size={15} /> Document</button>
      <button type="button" className={recording ? "recording voice-trigger" : "voice-trigger"} onClick={onVoice}><Mic size={15} /> {recording ? "Listening locally" : "Voice"}</button>
      <select className="answer-style-select" value={answerDetail} onChange={(event) => setAnswerDetail(event.target.value as "Concise" | "Standard" | "Detailed")} aria-label="Answer detail">
        <option>Concise</option><option>Standard</option><option>Detailed</option>
      </select>
      <select className="answer-style-select" value={readingLevel} onChange={(event) => setReadingLevel(event.target.value as "Standard" | "Plain")} aria-label="Reading level">
        <option>Standard</option><option>Plain</option>
      </select>
      <span className="composer-privacy"><ShieldCheck size={13} /> Private session</span>
    </div>
    <textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={onKeyDown} placeholder="Ask a health question, review a document, or prepare for a visit…" rows={3} />
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
  const emptyTitle = context === "document-review" ? "Document review in progress" : "Citations appear beside answers";
  const emptyBody = context === "document-review"
    ? "Review extracted values first. Approved sources appear after you confirm and request an explanation."
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

const DOC_STATUS_LABELS: Record<DocFieldStatus, string> = {
  in_listed_range: "",
  outside_listed_range: "",
  flagged_high_on_report: "Flagged high on this report",
  flagged_low_on_report: "Flagged low on this report",
  not_applicable: "",
  unknown: "",
};
const DOC_CONFIDENCE_LABELS: Record<DocFieldConfidence, string> = { clearly_visible: "Clearly visible", needs_review: "Needs review", could_not_read: "Could not read" };

export function Documents({
  apiUrl, docState, docFields, docConfirmed, docReviewChecked, setDocReviewChecked,
  docSelectedPage, setDocSelectedPage, highlightedFieldId, setHighlightedFieldId,
  docExplain, docQuestion, setDocQuestion,
  selectedSource, setSelectedSource,
  dragging, recentSessions, onOpenSession, onUpload, onLoadSample, demoGuide, onOpenLabsFromDemo, onDrop, onDragEnter, onDragLeave, onFieldChange, onConfirm, onExplain, onSuggestQuestions, onPrepareVisit, onAskAbout, onExportFields, onOpenLabs, onReset,
  loading, error, errorKind, labsHint, confirmedLabCodes, onRetry, onSystem, onRemove, onOpenImaging,
  processStage, processFailed, processRetry, fieldReviewState, setFieldReviewState, previewZoom, setPreviewZoom, sourceBreadcrumb, onClearBreadcrumb, onBackToTimeline,
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
  onFieldChange: (fieldId: string, patch: Partial<Pick<DocField, "value" | "unit" | "reference_range">>) => void;
  onConfirm: () => void;
  onExplain: () => void;
  onSuggestQuestions: () => void;
  onPrepareVisit: () => void;
  onAskAbout: () => void;
  onExportFields: () => void;
  onOpenLabs: () => void;
  onReset: () => void;
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
  fieldReviewState: Record<string, "unverified" | "confirmed" | "corrected" | "rejected">;
  setFieldReviewState: (value: Record<string, "unverified" | "confirmed" | "corrected" | "rejected"> | ((prev: Record<string, "unverified" | "confirmed" | "corrected" | "rejected">) => Record<string, "unverified" | "confirmed" | "corrected" | "rejected">)) => void;
  previewZoom: number;
  setPreviewZoom: (value: number) => void;
  sourceBreadcrumb: string;
  onClearBreadcrumb: () => void;
  onBackToTimeline: () => void;
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
  const reviewedCount = docFields.filter((field) => fieldReviewState[field.field_id] && fieldReviewState[field.field_id] !== "unverified").length;

  if (!docState) {
    return <div className="workflow-view">
      <div className="workflow-heading-row">
        <div>
          <p className="eyebrow">DOCUMENTS</p>
          <h2>Documents</h2>
          <p className="workflow-lead">Upload, review, and trace information from your health documents.</p>
        </div>
        <div className="heading-actions">
          <button className="forest-button" type="button" onClick={onUpload}><Plus size={15} /> Upload document</button>
          <button className="quiet-button" type="button" onClick={onLoadSample}>Try synthetic report</button>
        </div>
      </div>
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
                <td>{session.confirmed ? "Verified" : "Needs review"}</td>
                <td><StatusChip label={session.confirmed ? "Ready" : session.status.replaceAll("_", " ")} tone={session.confirmed ? "success" : "neutral"} /></td>
                <td><button type="button" className="quiet-button" onClick={() => onOpenSession(session.document_id)}>Open</button></td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>}
    </div>;
  }

  const visibleFields = docFields.filter((field) => field.page_number === docSelectedPage);
  const activePreview = docState.pages.find((page) => page.page_number === docSelectedPage) || docState.pages[0];

  if ((loading || processStage) && !docFields.length) {
    return <div className="workflow-view doc-intel-view">
      <div className="workflow-heading-row">
        <div>
          <p className="eyebrow">DOCUMENTS</p>
          <h2>{docState.filename}</h2>
          <p className="workflow-lead">Processing your document while keeping the original file available.</p>
        </div>
      </div>
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
    <div className="workflow-heading-row">
      <div>
        <p className="eyebrow">DOCUMENT REVIEW</p>
        <h2>{docState.filename}</h2>
        <p className="workflow-lead">{docState.page_count} page{docState.page_count === 1 ? "" : "s"} · {docConfirmed ? "Confirmed by you" : "Information found in your report — review before confirming"}</p>
      </div>
      <div className="heading-actions">
        {docFields.length > 0 && <button className="quiet-button" onClick={onExportFields}><Clipboard size={14} /> Export fields</button>}
        <button className="quiet-button" onClick={onReset}><Trash2 size={14} /> Delete document</button>
      </div>
    </div>

    {sourceBreadcrumb && (
      <div className="source-breadcrumb" aria-label="Source navigation">
        <span>{sourceBreadcrumb}</span>
        <button type="button" className="quiet-button" onClick={() => { onClearBreadcrumb(); onBackToTimeline(); }}>← Back to Hemoglobin A1C</button>
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
    {demoGuide && <p className="demo-guide-banner">{demoGuide}{docConfirmed ? <>{" "}<button type="button" className="quiet-button" onClick={onOpenLabsFromDemo}>Open Labs</button></> : null}</p>}
    {labsHint && <div className="labs-persist-hint-row">
      <p className="labs-persist-hint"><FlaskConical size={14} /> {labsHint}</p>
      {confirmedLabCodes.length > 0 && <button type="button" className="quiet-button" onClick={onOpenLabs}><TrendingUp size={14} /> View in Labs</button>}
    </div>}

    {docState.page_count >= 1 && <div className="page-nav-bar" aria-label="Page navigation">
      <button type="button" className="quiet-button" disabled={docSelectedPage <= 1} onClick={() => setDocSelectedPage(Math.max(1, docSelectedPage - 1))}>Previous</button>
      <span>Page {docSelectedPage} of {docState.page_count}</span>
      <button type="button" className="quiet-button" disabled={docSelectedPage >= docState.page_count} onClick={() => setDocSelectedPage(Math.min(docState.page_count, docSelectedPage + 1))}>Next</button>
      <button type="button" className="quiet-button" onClick={() => setPreviewZoom(1)}><ZoomIn size={14} /> Fit width</button>
      <button type="button" className="quiet-button" onClick={() => setPreviewZoom(Math.min(1.6, previewZoom + 0.15))}>Zoom in</button>
      <button type="button" className="quiet-button" onClick={() => setPreviewZoom(Math.max(0.8, previewZoom - 0.15))}>Zoom out</button>
    </div>}

    <div className="extraction-grid doc-review-grid">
      <div className="document-preview doc-page-preview">
        <p className="panel-kicker">ORIGINAL REPORT · PAGE {docSelectedPage}</p>
        {activePreview?.preview_url ? <AuthImage src={`${apiUrl}${activePreview.preview_url}`} alt={`Page ${docSelectedPage} preview`} style={{ transform: `scale(${previewZoom})`, transformOrigin: "top center" }} /> : <div className="doc-preview-placeholder"><FileText size={38} /><span>Page {docSelectedPage} preview</span></div>}
        <small>Check names, values, units, dates, and reference ranges against the source page</small>
      </div>

      <div className="extracted-fields doc-fields">
        <p className="eyebrow">{docConfirmed ? "CONFIRMED" : "VERIFICATION"} · PAGE {docSelectedPage}</p>
        <h3 className="doc-fields-heading">Extracted lab information</h3>
        <p className="doc-fields-support">Information found in your report — confirm before it enters the timeline</p>
        {!docConfirmed && docFields.length > 0 && <p className="review-progress">{reviewedCount} of {docFields.length} reviewed</p>}
        {visibleFields.length === 0 && <p className="doc-fields-empty">No information was found on this page.</p>}
        {visibleFields.map((field) => (
          <div
            key={field.field_id}
            className={`doc-field-row status-${field.status}${highlightedFieldId === field.field_id ? " field-highlighted" : ""}`}
            onFocus={() => setHighlightedFieldId(field.field_id)}
          >
            <div className="doc-field-label">
              <strong>{field.label}</strong>
              <span className={`confidence-pill confidence-${field.confidence}`}>{DOC_CONFIDENCE_LABELS[field.confidence]}</span>
              <span className="status-chip">{fieldReviewState[field.field_id] === "corrected" ? "Corrected" : fieldReviewState[field.field_id] === "rejected" ? "Rejected" : fieldReviewState[field.field_id] === "confirmed" || docConfirmed ? "Confirmed" : "Unverified"}</span>
              {(field.status === "flagged_high_on_report" || field.status === "flagged_low_on_report") && DOC_STATUS_LABELS[field.status] ? (
                <span className={`status-pill status-pill-${field.status}`}>{DOC_STATUS_LABELS[field.status]}</span>
              ) : null}
            </div>
            <div className="doc-field-inputs">
              <label>Value<input value={field.value} readOnly={docConfirmed} onChange={(event) => onFieldChange(field.field_id, { value: event.target.value })} /></label>
              <label>Unit<input value={field.unit} readOnly={docConfirmed} onChange={(event) => onFieldChange(field.field_id, { unit: event.target.value })} /></label>
              <label>Reference range<input value={field.reference_range} readOnly={docConfirmed} onChange={(event) => onFieldChange(field.field_id, { reference_range: event.target.value })} /></label>
            </div>
            {!docConfirmed && (
              <div className="field-review-actions">
                <button type="button" className="quiet-button" onClick={() => setFieldReviewState((current) => ({ ...current, [field.field_id]: "confirmed" }))}>Confirm</button>
                <button type="button" className="quiet-button" onClick={() => setHighlightedFieldId(field.field_id)}>Edit</button>
                <button type="button" className="quiet-button" onClick={() => setFieldReviewState((current) => ({ ...current, [field.field_id]: "rejected" }))}>Reject</button>
              </div>
            )}
          </div>
        ))}

        {!docConfirmed && <div className="confirm-gate">
          <label className="confirm"><input type="checkbox" checked={docReviewChecked} onChange={(event) => setDocReviewChecked(event.target.checked)} /> I reviewed the names, values, units, dates, and reference ranges above.</label>
          <button className="forest-button" disabled={!docReviewChecked || Boolean(loading)} onClick={onConfirm}>Confirm reviewed items <Check size={16} /></button>
        </div>}

        {docConfirmed && !docExplain && <div className="explain-gate">
          <label>Ask a question about this document (optional)<textarea rows={2} value={docQuestion} onChange={(event) => setDocQuestion(event.target.value)} placeholder="Explain the confirmed information in plain language and suggest questions for a qualified healthcare professional." /></label>
          <div className="explain-actions">
            <button className="quiet-button" type="button" onClick={onOpenLabs}><FlaskConical size={15} /> Open Labs</button>
            <button className="quiet-button" type="button" onClick={onPrepareVisit}><Stethoscope size={15} /> Prepare visit questions</button>
            <button className="quiet-button" type="button" onClick={onAskAbout}><Sparkles size={15} /> Ask about these values</button>
            <button className="quiet-button" type="button" onClick={onSuggestQuestions}>Suggest questions</button>
            <button className="forest-button" disabled={Boolean(loading)} onClick={onExplain}>Understand this result <ArrowUpRight size={16} /></button>
          </div>
        </div>}
        {docConfirmed && docExplain && <div className="explain-actions">
          <button className="quiet-button" type="button" onClick={onOpenLabs}><FlaskConical size={15} /> Open Labs</button>
          <button className="quiet-button" type="button" onClick={onPrepareVisit}><Stethoscope size={15} /> Prepare visit questions</button>
          <button className="quiet-button" type="button" onClick={onAskAbout}><Sparkles size={15} /> Ask about these values</button>
        </div>}
      </div>
    </div>

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
  apiUrl, medState, medFields, medConfirmed, medReviewChecked, setMedReviewChecked,
  medInfo, medQuestion, setMedQuestion, medTypedText, setMedTypedText,
  selectedSource, setSelectedSource,
  dragging, onUpload, onDrop, onDragEnter, onDragLeave, onFieldChange, onConfirm, onGetInfo, onSubmitTyped, onSample, onPrepareVisit, onReset,
  loading, error,
}: {
  apiUrl: string;
  medState: MedState | null;
  medFields: MedField[];
  medConfirmed: boolean;
  medReviewChecked: boolean;
  setMedReviewChecked: (value: boolean) => void;
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
  onFieldChange: (key: string, value: string) => void;
  onConfirm: () => void;
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
      <div className="workflow-heading-row">
        <div><p className="eyebrow">MEDICATION WORKSPACE</p><h2>Understand a medication label.</h2><p className="workflow-lead">Upload a photo of a label, or type what is printed on it — review the extracted name, strength, and instructions before MediGuide adds educational information.</p></div>
        <span className="workflow-badge"><ShieldCheck size={14} /> Human review first</span>
      </div>
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
    </div>;
  }

  return <div className="workflow-view doc-intel-view">
    <div className="workflow-heading-row">
      <div><p className="eyebrow">MEDICATION WORKSPACE</p><h2>{medState.filename || "Typed label"}</h2><p className="workflow-lead">{medConfirmed ? "Confirmed by you" : "Review each detail before confirming"}</p></div>
      <button className="quiet-button" onClick={onReset}><RefreshCw size={14} /> Start over</button>
    </div>

    {error && <div className="service-error"><Activity size={19} /><div><strong>{error}</strong><p>Try again below.</p></div></div>}

    <div className="extraction-grid doc-review-grid">
      <div className="document-preview doc-page-preview">
        {medState.source === "upload" ? <AuthImage src={`${apiUrl}${medState.preview_url}`} alt="Label preview" /> : <Pill size={38} />}
        <small>Check the medication name, strength, and directions</small>
      </div>

      <div className="extracted-fields doc-fields">
        <p className="eyebrow">EXTRACTED DETAILS</p>
        {medFields.map((field) => (
          <div key={field.key} className="doc-field-row">
            <div className="doc-field-label">
              <strong>{field.label}</strong>
              <span className={`confidence-pill confidence-${field.confidence}`}>{DOC_CONFIDENCE_LABELS[field.confidence]}</span>
            </div>
            <div className="doc-field-inputs">
              <label>Value<input value={field.value} readOnly={medConfirmed} onChange={(event) => onFieldChange(field.key, event.target.value)} /></label>
            </div>
          </div>
        ))}
        {medState.other_visible_text && <p className="doc-fields-empty">Other visible text: {medState.other_visible_text}</p>}

        {!medConfirmed && <div className="confirm-gate">
          <label className="confirm"><input type="checkbox" checked={medReviewChecked} onChange={(event) => setMedReviewChecked(event.target.checked)} /> I reviewed the medication name, strength, and instructions above.</label>
          <button className="forest-button" disabled={!medReviewChecked || Boolean(loading)} onClick={onConfirm}>Confirm reviewed details <Check size={16} /></button>
        </div>}

        {medConfirmed && !medInfo && <div className="explain-gate">
          <label>Ask a question about this medication (optional)<textarea rows={2} value={medQuestion} onChange={(event) => setMedQuestion(event.target.value)} placeholder="What should I know about this medication?" /></label>
          <div className="explain-actions">
            <button className="quiet-button" type="button" onClick={onPrepareVisit}><Stethoscope size={15} /> Add to visit prep</button>
            <button className="forest-button" disabled={Boolean(loading)} onClick={onGetInfo}>Get educational information <ArrowUpRight size={16} /></button>
          </div>
        </div>}
        {medConfirmed && medInfo && <div className="explain-actions">
          <button className="quiet-button" type="button" onClick={onPrepareVisit}><Stethoscope size={15} /> Add to visit prep</button>
        </div>}
      </div>
    </div>

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
      lines.push(`- ${point.test_name}: ${point.value_text} ${point.unit}${point.report_date ? ` (${point.report_date})` : ""}`);
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

export function Visit({ fields, setFields, step, setStep, labPoints, medFields, onGenerate }: { fields: Record<string, string>; setFields: (value: Record<string, string>) => void; step: number; setStep: (value: number) => void; labPoints: LabPoint[]; medFields: MedField[]; onGenerate: () => void }) {
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
    <p className="eyebrow">VISIT PREPARATION</p>
    <h2>Make the visit count.</h2>
    <p className="workflow-lead">Organize patient-provided information into a clear visit preparation summary.</p>
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
        <button type="button" className="forest-button" onClick={onGenerate}>Continue in conversation <ArrowUpRight size={16} /></button>
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
    <p className="eyebrow">DEMO MODE</p>
    <h2>Try with synthetic data.</h2>
    <p className="workflow-lead">One click loads a three-date synthetic lab report (January, April, August). No personal medical information is required.</p>
    <button type="button" className="forest-button demo-hero-cta" onClick={onSyntheticPipeline}>
      <PlayCircle size={18} /> Try with synthetic data
    </button>
    <p className="demo-pipeline-caption">Walkthrough: extraction → verification → Labs → explanation → source-page drill-down</p>
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
      <p className="eyebrow">EVALUATION</p>
      <h2>Engineering evaluation</h2>
      <p className="workflow-lead">Synthetic test metrics for portfolio review. Protected from casual browsing.</p>
      <div className="eval-gate">
        <Lock size={18} />
        <p>Unlock to view synthetic evaluation results.</p>
        <button type="button" className="forest-button" onClick={() => setUnlocked(true)}>Unlock for portfolio demo</button>
      </div>
    </div>;
  }
  return <div className="workflow-view">
    <div className="eval-banner"><Lock size={14} /> Engineering evaluation (synthetic tests — no patient data)</div>
    <p className="eyebrow">EVALUATION</p>
    <h2>Safety &amp; quality metrics</h2>
    <p className="workflow-lead">Results from synthetic regression suites used in engineering review.</p>
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
  onAskAbout: () => void;
  onRequestDeleteObservation: (observationId: string) => void;
  onOpenDocuments: () => void;
}) {
  const maxValue = Math.max(...points.map((point) => point.value ?? 0), 1);
  const activeTest = (tests.find((test) => test.test_code === selectedCode)?.display_name) || selectedCode;
  const selectedDate = selectedPoint?.collection_date || selectedPoint?.report_date;
  const selectedPage = selectedPoint?.source_page || selectedPoint?.page_number || 1;
  const selectedReference = selectedPoint?.reference_range || selectedPoint?.reference_text;
  const selectedVerification = selectedPoint?.verification_status || selectedPoint?.verification_state;
  const reportFlag = reportFlagLabel(selectedPoint?.range_status);
  const uniqueDocuments = new Set(points.map((point) => point.document_id)).size;
  const extractionConfidence = confidenceLabel(selectedPoint?.confidence);
  const latest = points.length ? points[points.length - 1] : null;

  return <div className="workflow-view lab-timeline-view">
    <div className="workflow-heading-row">
      <div>
        <p className="eyebrow">LAB TIMELINE</p>
        <h2>Labs</h2>
        <p className="workflow-lead">Explore verified measurements across reports.</p>
      </div>
      <div className="heading-actions">
        <label className="timeline-control">
          <span className="sr-only">Test selector</span>
          <select value={selectedCode} onChange={(event) => onSelectCode(event.target.value)} aria-label="Test selector">
            {(tests.length ? tests : [{ test_code: "hemoglobin_a1c", display_name: "Hemoglobin A1C", observation_count: 0, has_data: false }]).map((test) => (
              <option key={test.test_code} value={test.test_code}>{test.display_name}</option>
            ))}
          </select>
        </label>
        <button type="button" className="quiet-button" onClick={onAskAbout} disabled={!points.length}><Sparkles size={14} /> Understand this result</button>
        <button type="button" className="quiet-button" onClick={onAddToVisit}><Stethoscope size={14} /> Add to visit prep</button>
        <button type="button" className="quiet-button" onClick={onExport} disabled={!points.length}><Clipboard size={14} /> Export CSV</button>
      </div>
    </div>

    {latest && (
      <div className="latest-result-card">
        <p className="panel-kicker">Latest verified result · {activeTest}</p>
        <p className="lab-result-value">{latest.value_text} {latest.unit}</p>
        <p className="lab-result-date">{formatCollectionDate(latest.collection_date || latest.report_date)}</p>
        {reportFlagLabel(latest.range_status) ? <p className="lab-range-flag">{reportFlagLabel(latest.range_status)}</p> : null}
        {(latest.reference_range || latest.reference_text) ? <p className="latest-ref">Printed reference range: {latest.reference_range || latest.reference_text}</p> : null}
      </div>
    )}

    <div className="lab-chart-panel">
      {points.length ? (
        <div className="lab-chart" role="list" aria-label={`${activeTest} timeline`}>
          {points.map((point) => {
            const height = Math.max(12, ((point.value ?? 0) / maxValue) * 100);
            return <button type="button" key={point.observation_id} className={selectedPoint?.observation_id === point.observation_id ? "lab-point selected" : "lab-point"} style={{ height: `${height}%` }} onClick={() => onSelectPoint(point)} role="listitem" title={`${point.value_text} ${point.unit}`}>
              <span className="lab-point-dot" />
              <strong>{point.value_text}</strong>
              <small>{formatCollectionDate(point.collection_date || point.report_date)}</small>
            </button>;
          })}
        </div>
      ) : (
        <EmptyState
          title="No verified measurements yet"
          body="Verified measurements will appear here after document review."
        >
          <button type="button" className="forest-button" onClick={onOpenDocuments}>Review documents</button>
        </EmptyState>
      )}
    </div>
    {points.length > 0 && <p className="lab-timeline-summary">{points.length} verified measurement{points.length === 1 ? "" : "s"} · {uniqueDocuments} source report{uniqueDocuments === 1 ? "" : "s"}</p>}
    {points.length > 0 && <table className="lab-table">
      <caption className="sr-only">{activeTest} verified measurements</caption>
      <thead><tr><th>Date</th><th>Result</th><th>Report flag</th><th>Source</th></tr></thead>
      <tbody>
        {points.map((point) => (
          <tr key={point.observation_id} className={selectedPoint?.observation_id === point.observation_id ? "selected" : ""} onClick={() => onSelectPoint(point)}>
            <td>{formatCollectionDate(point.collection_date || point.report_date)}</td>
            <td>{point.value_text} {point.unit}</td>
            <td>{point.source_flag === "H" ? "High" : point.source_flag === "L" ? "Low" : reportFlagLabel(point.range_status) || "—"}</td>
            <td>{point.document_name}</td>
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
        <p className="lab-result-date">{formatCollectionDate(selectedDate)}</p>
        {reportFlag ? <p className="lab-range-flag">{reportFlag}</p> : null}
        <p className="panel-kicker">REPORT INFORMATION</p>
        <dl>
          <div><dt>Printed reference range</dt><dd>{selectedReference || "Not listed on report"}</dd></div>
          <div><dt>Report flag</dt><dd>{selectedPoint.source_flag === "H" ? "High" : selectedPoint.source_flag === "L" ? "Low" : reportFlag || "None listed"}</dd></div>
        </dl>
        <p className="panel-kicker">VERIFICATION</p>
        <dl>
          <div><dt>Status</dt><dd>{selectedVerification === "confirmed" || selectedVerification === "human_verified" ? "✓ Confirmed" : (selectedVerification || "Unknown")}</dd></div>
          {extractionConfidence ? <div><dt>Extraction quality</dt><dd>{extractionConfidence} <small className="confidence-note">(extraction only — not medical correctness)</small></dd></div> : null}
        </dl>
        <p className="panel-kicker">SOURCE</p>
        <dl>
          <div><dt>Document</dt><dd>{selectedPoint.document_name}</dd></div>
          <div><dt>Page</dt><dd>{selectedPage}</dd></div>
          {selectedPoint.extracted_value != null && <div><dt>Extracted value</dt><dd>{selectedPoint.extracted_value}</dd></div>}
          {selectedPoint.confirmed_value != null && <div><dt>Confirmed value</dt><dd>{selectedPoint.confirmed_value}</dd></div>}
        </dl>
        <div className="lab-point-actions">
          <button type="button" className="forest-button" onClick={() => onInspectDocument(selectedPoint.document_id, selectedPage, selectedPoint.field_id)}>
            <FileText size={14} /> View source page
          </button>
          <button type="button" className="quiet-button" onClick={onAskAbout}><Sparkles size={14} /> Understand this result</button>
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
    <p className="eyebrow">SYSTEM</p>
    <h2>System Status</h2>
    <p className="workflow-lead">Service availability for document processing and educational features. Documents and verified information remain accessible when explanations are limited.</p>
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
  return <div className="workflow-view"><p className="eyebrow">SOURCE EVIDENCE</p><h2>Approved sources.</h2><p className="workflow-lead">Trusted local retrieval keeps educational explanations grounded. Lab values use a separate provenance chain back to the original report page.</p><Input className="source-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search publishers or titles..." aria-label="Search approved sources" /><div className="source-list">{filtered.length ? filtered.map((source) => <a key={source.id} href={source.url || undefined} target={source.url ? "_blank" : undefined} rel={source.url ? "noreferrer" : undefined} className={source.url ? "" : "no-link"}><span><BookOpen size={15} /></span><div><strong>{source.publisher}</strong><b>{source.title}</b><small>{source.reviewed ? `Reviewed ${source.reviewed}` : "Approved source"}</small></div>{source.url && <ArrowUpRight size={16} />}</a>) : <div className="empty-panel"><BookOpen size={23} /><p>{library.length ? "No sources match that search." : "No approved sources are available yet."}</p></div>}</div></div>;
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
