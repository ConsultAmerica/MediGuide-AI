"use client";

import { useRouter } from "next/navigation";
import { Documents } from "../workspace-views";
import { useWorkspaceContext } from "../_state/WorkspaceStateProvider";
import { API_URL } from "../_state/workspace-shared";

// Shared by the list route (/workspace/documents) and the per-document route
// (/workspace/documents/[id]) — both just render the current context state
// through the same view; only how that state gets populated differs.
export function DocumentsView() {
  const router = useRouter();
  const {
    docState, docFields, docConfirmed, docReviewChecked, setDocReviewChecked,
    docSelectedPage, setDocSelectedPage, highlightedFieldId, setHighlightedFieldId,
    docExplain, docQuestion, setDocQuestion, selectedSource, setSelectedSource,
    documentDragging, setDocumentDragging, recentSessions,
    inspectDocument, fileInput, loadSampleLabReport, demoGuide, setDemoGuide,
    handleViewChange, onDrop, updateDocField, confirmDocument, explainDocument,
    suggestDocumentQuestions, prepareVisitFromDocument, askAboutDocument,
    exportDocumentFields, confirmedLabCodes, openLabTimeline, setConfirmResetDocument,
    loadingStage, error, docErrorKind, addConfirmedLabsHint, retryDocumentAction, rereadDocument,
    processStage, processFailed, processRetry, fieldReviewState, draftStatus, setFieldDecision, undoFieldReview,
    previewZoom, setPreviewZoom, sourceBreadcrumb, setSourceBreadcrumb, aiAvailable, chatAvailable,
  } = useWorkspaceContext();

  return (
    <Documents
      apiUrl={API_URL}
      docState={docState}
      docFields={docFields}
      docConfirmed={docConfirmed}
      docReviewChecked={docReviewChecked}
      setDocReviewChecked={setDocReviewChecked}
      docSelectedPage={docSelectedPage}
      setDocSelectedPage={setDocSelectedPage}
      highlightedFieldId={highlightedFieldId}
      setHighlightedFieldId={setHighlightedFieldId}
      docExplain={docExplain}
      docQuestion={docQuestion}
      setDocQuestion={setDocQuestion}
      selectedSource={selectedSource}
      setSelectedSource={setSelectedSource}
      dragging={documentDragging}
      recentSessions={recentSessions}
      onOpenSession={(documentId) => void inspectDocument(documentId, 1)}
      onUpload={() => fileInput.current?.click()}
      onLoadSample={() => void loadSampleLabReport()}
      demoGuide={demoGuide}
      onOpenLabsFromDemo={() => { setDemoGuide("Step 2 of 4 — Labs: Click a measurement (try 6.7%), then View source page."); handleViewChange("labs"); }}
      onDrop={onDrop}
      onDragEnter={() => setDocumentDragging(true)}
      onDragLeave={() => setDocumentDragging(false)}
      onFieldChange={updateDocField}
      onConfirm={() => void confirmDocument()}
      onExplain={aiAvailable ? () => void explainDocument() : undefined}
      onSuggestQuestions={suggestDocumentQuestions}
      onPrepareVisit={prepareVisitFromDocument}
      onAskAbout={chatAvailable ? askAboutDocument : undefined}
      onExportFields={exportDocumentFields}
      onOpenLabs={() => openLabTimeline(confirmedLabCodes[0])}
      onReset={() => setConfirmResetDocument(true)}
      onReread={() => void rereadDocument()}
      loading={loadingStage}
      error={error}
      errorKind={docErrorKind}
      labsHint={addConfirmedLabsHint}
      confirmedLabCodes={confirmedLabCodes}
      onRetry={retryDocumentAction}
      onSystem={() => handleViewChange("system")}
      onRemove={() => setConfirmResetDocument(true)}
      onOpenImaging={() => router.push("/workspace/imaging")}
      processStage={processStage}
      processFailed={processFailed}
      processRetry={processRetry}
      fieldReviewState={fieldReviewState}
      draftStatus={draftStatus}
      onDecide={setFieldDecision}
      onUndo={undoFieldReview}
      previewZoom={previewZoom}
      setPreviewZoom={setPreviewZoom}
      sourceBreadcrumb={sourceBreadcrumb}
      onClearBreadcrumb={() => setSourceBreadcrumb("")}
      onBackToSource={() => router.back()}
    />
  );
}
