import { useEffect, useState } from "react";
import { ArrowLeft, GitCompare, History, Maximize2, Minimize2, ScanLine, Trash2 } from "lucide-react";
import {
  MODALITY_LABELS,
  formatStudyDate,
  type FindingExplanation,
  type ImagingFinding,
  type ImagingStudy,
  type ReportGap,
  type ReportSection,
  deriveReportState,
} from "./imaging-types";
import { ImagingStatusChip } from "./ImagingStatusChip";
import { ImagingReportPanel } from "./ImagingReportPanel";
import { ImagingOverviewPanel } from "./ImagingOverviewPanel";
import { ImagingFindingsReview } from "./ImagingFindingsReview";
import { ImagingFindingDrawer } from "./ImagingFindingDrawer";
import { ImagingNoReportEmptyState } from "./ImagingEmptyState";
import { ImagingProcessingState } from "./ImagingProcessingState";
import { ImagingProcessingFailedState } from "./ImagingErrorState";
import { reportPagePreviewUrl } from "./imaging-api";
import { AuthImage } from "../_components/AuthImage";

type DetailTab = "overview" | "report" | "images" | "explanation" | "source";

export function ImagingStudyDetail({
  apiUrl,
  study,
  sections,
  findings,
  gaps,
  boundary,
  editedSections,
  setEditedSections,
  reviewedTypes,
  setReviewedTypes,
  findingDrafts,
  setFindingDrafts,
  reviewedFindingIds,
  setReviewedFindingIds,
  selectedPage,
  setSelectedPage,
  viewerExpanded,
  setViewerExpanded,
  transientStatus,
  processingError,
  processingProgress,
  confirming,
  confirmingFindings,
  onBack,
  onOpenHistory,
  onOpenCompare,
  onUploadReport,
  onRetryUpload,
  onViewExistingReport,
  onConfirm,
  onConfirmFindings,
  onExplainFinding,
  findingExplanation,
  findingExplainLoading,
  onRequestDelete,
  onOpenTerminology,
  onAddToVisit,
  onOpenSourceDocument,
}: {
  apiUrl: string;
  study: ImagingStudy;
  sections: ReportSection[];
  findings: ImagingFinding[];
  gaps: ReportGap[];
  boundary: string;
  editedSections: Record<string, string>;
  setEditedSections: (value: Record<string, string>) => void;
  reviewedTypes: Set<string>;
  setReviewedTypes: (value: Set<string>) => void;
  findingDrafts: Record<string, string>;
  setFindingDrafts: (value: Record<string, string>) => void;
  reviewedFindingIds: Set<string>;
  setReviewedFindingIds: (value: Set<string>) => void;
  selectedPage: number;
  setSelectedPage: (value: number) => void;
  viewerExpanded: boolean;
  setViewerExpanded: (value: boolean) => void;
  transientStatus: "processing" | "failed" | null;
  processingError: string;
  processingProgress: { stage: string; retryAttempt: number; retryMax: number } | null;
  confirming: boolean;
  confirmingFindings: boolean;
  onBack: () => void;
  onOpenHistory: () => void;
  onOpenCompare: () => void;
  onUploadReport: (file: File) => void;
  onRetryUpload: () => void;
  onViewExistingReport: () => void;
  onConfirm: () => void;
  onConfirmFindings: (updates: { finding_id: string; confirmed_text: string; verification_status: string }[]) => void;
  onExplainFinding: (finding: ImagingFinding) => void;
  findingExplanation: FindingExplanation | null;
  findingExplainLoading: boolean;
  onRequestDelete: () => void;
  onOpenTerminology: (term: string, sourceExcerpt: string) => void;
  onAddToVisit: () => void;
  onOpenSourceDocument: (documentId: string, page: number) => void;
}) {
  const state = deriveReportState(study, sections, transientStatus);
  const previewUrl = study.report_document_id ? reportPagePreviewUrl(apiUrl, study.study_id, selectedPage) : "";
  const confirmedFindings = findings.filter((f) => f.verification_status === "confirmed");
  const pendingFindings = findings.filter((f) => f.verification_status === "unverified");
  const canShowOverview = confirmedFindings.length > 0;

  const [tab, setTab] = useState<DetailTab>(canShowOverview ? "overview" : "report");
  const [previewFailed, setPreviewFailed] = useState(false);
  const [activeFinding, setActiveFinding] = useState<ImagingFinding | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPreviewFailed(false);
  }, [previewUrl]);

  useEffect(() => {
    if (study.verification_status === "verified" && canShowOverview) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setTab("overview");
    }
  }, [study.verification_status, canShowOverview]);

  const showPreviewImage = Boolean(previewUrl) && !previewFailed;
  const title =
    study.study_description?.trim() ||
    [MODALITY_LABELS[study.modality], study.body_region].filter(Boolean).join(" · ") ||
    MODALITY_LABELS[study.modality];

  function viewSourcePage(pageNumber: number, documentId?: string) {
    setSelectedPage(pageNumber);
    setTab("source");
    setViewerExpanded(true);
    // A finding from this study's own report is shown right here, on the
    // Source tab. Imaging reports have no Documents review session, so
    // routing them to /workspace/documents would only reach a 404.
    if (documentId && documentId !== study.report_document_id) onOpenSourceDocument(documentId, pageNumber);
  }

  return (
    <div className="workflow-view imaging-study-detail">
      <button type="button" className="quiet-button imaging-back" onClick={onBack}>
        <ArrowLeft size={14} /> Imaging / {MODALITY_LABELS[study.modality]}
      </button>

      <div className="document-meta imaging-study-meta">
        <ScanLine size={18} aria-hidden="true" />
        <span>
          <h2>{title}</h2>
          <small>
            {formatStudyDate(study.study_date)}
            {study.institution ? ` · ${study.institution}` : ""}
          </small>
        </span>
        <ImagingStatusChip state={state} />
      </div>

      <p className="imaging-boundary imaging-image-boundary">
        MediGuide explains the radiologist&apos;s report. It does not independently diagnose the scan.
      </p>

      <div className="imaging-detail-actions">
        <button type="button" className="quiet-button" onClick={onOpenHistory}>
          <History size={14} /> View history
        </button>
        <button type="button" className="quiet-button" onClick={onOpenCompare}>
          <GitCompare size={14} /> Compare
        </button>
        <button type="button" className="quiet-button imaging-delete" onClick={onRequestDelete}>
          <Trash2 size={14} /> Delete study
        </button>
      </div>

      {transientStatus === "processing" && <ImagingProcessingState progress={processingProgress} />}
      {transientStatus === "failed" && (
        <ImagingProcessingFailedState
          message={processingError}
          onRetry={onRetryUpload}
          onViewReport={study.report_document_id ? onViewExistingReport : undefined}
        />
      )}

      {!study.report_document_id && !transientStatus ? (
        <ImagingNoReportEmptyState onAttach={onUploadReport} />
      ) : study.report_document_id && !transientStatus ? (
        <>
          <nav className="imaging-detail-tabs" aria-label="Study sections">
            {(
              [
                ["overview", "Overview", canShowOverview, null as number | null],
                ["report", "Report", true, pendingFindings.length || null],
                ["images", "Images", true, null],
                ["explanation", "Explanation", canShowOverview, null],
                ["source", "Source", true, null],
              ] as const
            ).map(([id, label, enabled, badge]) => (
              <button
                key={id}
                type="button"
                className={tab === id ? "active" : ""}
                disabled={!enabled}
                onClick={() => {
                  setTab(id);
                  setViewerExpanded(id === "source" || id === "images");
                }}
              >
                {label}
                {badge ? <span className="imaging-tab-badge">{badge}</span> : null}
              </button>
            ))}
          </nav>

          {(tab === "overview" || tab === "explanation") && canShowOverview ? (
            <ImagingOverviewPanel
              study={study}
              sections={sections.filter((s) => s.verification_status === "confirmed")}
              findings={findings}
              gaps={gaps}
              boundary={boundary}
              onViewSourcePage={viewSourcePage}
              onUnderstandFinding={(finding) => {
                setActiveFinding(finding);
                onExplainFinding(finding);
              }}
              onAddToVisit={onAddToVisit}
            />
          ) : null}

          {tab === "report" ? (
            <div className="extraction-grid imaging-detail-grid">
              <div className="document-preview imaging-viewer">
                {showPreviewImage ? (
                  <AuthImage src={previewUrl} alt={`Page ${selectedPage}`} onError={() => setPreviewFailed(true)} />
                ) : (
                  <span>No preview is available for this page.</span>
                )}
                <div className="imaging-page-nav">
                  <button type="button" className="quiet-button" disabled={selectedPage <= 1} onClick={() => setSelectedPage(selectedPage - 1)}>
                    Previous page
                  </button>
                  <span>Page {selectedPage}</span>
                  <button type="button" className="quiet-button" onClick={() => setSelectedPage(selectedPage + 1)}>
                    Next page
                  </button>
                  <button type="button" className="quiet-button" aria-label="Expand" onClick={() => setViewerExpanded(true)}>
                    <Maximize2 size={14} />
                  </button>
                </div>
              </div>
              <div className="imaging-report-stack">
                <ImagingReportPanel
                  study={study}
                  sections={sections}
                  editedSections={editedSections}
                  setEditedSections={setEditedSections}
                  reviewedTypes={reviewedTypes}
                  setReviewedTypes={setReviewedTypes}
                  onConfirm={onConfirm}
                  confirming={confirming}
                  onViewSourcePage={(page) => viewSourcePage(page)}
                  onOpenTerminology={onOpenTerminology}
                />
                <ImagingFindingsReview
                  findings={findings}
                  drafts={findingDrafts}
                  setDrafts={setFindingDrafts}
                  reviewedIds={reviewedFindingIds}
                  setReviewedIds={setReviewedFindingIds}
                  confirming={confirmingFindings}
                  onConfirm={onConfirmFindings}
                />
              </div>
            </div>
          ) : null}

          {(tab === "images" || tab === "source") && (
            <div className="imaging-viewer-expanded">
              {viewerExpanded ? (
                <button type="button" className="quiet-button imaging-back" onClick={() => setViewerExpanded(false)}>
                  <Minimize2 size={14} /> Back
                </button>
              ) : null}
              <p className="imaging-source-banner">
                {tab === "source"
                  ? "Opening the correct report page. Exact highlighting appears only when bounding-box evidence exists."
                  : "Report page images are available when the upload includes page previews. MediGuide does not diagnose scan pixels."}
              </p>
              <div className="document-preview imaging-viewer imaging-viewer-full">
                {showPreviewImage ? (
                  <AuthImage src={previewUrl} alt={`Page ${selectedPage}`} onError={() => setPreviewFailed(true)} />
                ) : (
                  <span>No preview is available for this page.</span>
                )}
              </div>
            </div>
          )}
        </>
      ) : null}

      <ImagingFindingDrawer
        open={Boolean(activeFinding)}
        finding={activeFinding}
        explanation={findingExplanation}
        loading={findingExplainLoading}
        onClose={() => setActiveFinding(null)}
        onExplain={() => activeFinding && onExplainFinding(activeFinding)}
        onViewSource={() => activeFinding && viewSourcePage(activeFinding.source_page, activeFinding.source_document_id)}
        onRetry={() => activeFinding && onExplainFinding(activeFinding)}
      />
    </div>
  );
}
