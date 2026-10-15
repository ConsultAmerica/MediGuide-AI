import { useEffect, useRef, useState } from "react";
import { PageHero } from "../_components/PageHero";
import { ArrowLeft, GitCompare, History, Maximize2, Minimize2, ScanLine, Trash2 } from "lucide-react";
import {
  MODALITY_LABELS,
  formatStudyDate,
  type FindingExplanation,
  type ImagingFinding,
  SECTION_LABELS,
  type ImagingStudy,
  type ReportGap,
  type ReportLineItem,
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
import { ImagingPageViewer } from "./ImagingPageViewer";
import { ImagingReportDetails } from "./ImagingReportDetails";
import { ImagingBoundaryEditor } from "./ImagingBoundaryEditor";

export type DetailTab = "overview" | "report" | "images" | "explanation" | "source";
export const DETAIL_TABS: readonly DetailTab[] = ["overview", "report", "images", "explanation", "source"];

export function ImagingStudyDetail({
  apiUrl,
  study,
  sections,
  findings,
  gaps,
  boundary,
  busySection,
  onDecideSection,
  onLoadLines,
  onSaveBoundaries,
  savingBoundaries,
  applyingDetails,
  onApplyDetails,
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
  confirmingFindings,
  onBack,
  onOpenHistory,
  onOpenCompare,
  onUploadReport,
  onRetryUpload,
  onViewExistingReport,
  onConfirmFindings,
  onExplainFinding,
  findingExplanation,
  findingExplainLoading,
  onRequestDelete,
  onOpenTerminology,
  onAddToVisit,
  onOpenSourceDocument,
  initialTab,
  onTabChange,
}: {
  apiUrl: string;
  study: ImagingStudy;
  sections: ReportSection[];
  findings: ImagingFinding[];
  gaps: ReportGap[];
  boundary: string;
  busySection: string | null;
  onDecideSection: (sectionType: string, decision: "confirmed" | "rejected" | "unverified", text?: string) => Promise<boolean>;
  onLoadLines: () => Promise<{ lines: ReportLineItem[]; adjustable: boolean } | null>;
  onSaveBoundaries: (ranges: { section_type: string; line_start: number; line_end: number }[]) => Promise<boolean>;
  savingBoundaries: boolean;
  applyingDetails: boolean;
  onApplyDetails: (fields: string[]) => void;
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
  confirmingFindings: boolean;
  onBack: () => void;
  onOpenHistory: () => void;
  onOpenCompare: () => void;
  onUploadReport: (file: File) => void;
  onRetryUpload: () => void;
  onViewExistingReport: () => void;
  onConfirmFindings: (updates: { finding_id: string; confirmed_text: string; verification_status: string }[]) => void;
  onExplainFinding: (finding: ImagingFinding) => void;
  findingExplanation: FindingExplanation | null;
  findingExplainLoading: boolean;
  onRequestDelete: () => void;
  onOpenTerminology: (term: string, sourceExcerpt: string) => void;
  onAddToVisit: () => void;
  onOpenSourceDocument: (documentId: string, page: number) => void;
  /** Tab from the URL (e.g. after a refresh); otherwise one is chosen. */
  initialTab?: DetailTab | null;
  onTabChange?: (tab: DetailTab) => void;
}) {
  const state = deriveReportState(study, sections, transientStatus);
  const previewUrl = study.report_document_id ? reportPagePreviewUrl(apiUrl, study.study_id, selectedPage) : "";
  const confirmedFindings = findings.filter((f) => f.verification_status === "confirmed");
  const pendingFindings = findings.filter((f) => f.verification_status === "unverified");
  const canShowOverview = confirmedFindings.length > 0;

  const [tab, setTabState] = useState<DetailTab>(initialTab ?? (canShowOverview ? "overview" : "report"));
  // Once a tab was asked for (by the URL or a click), it is never
  // overridden by the automatic jump to Overview below.
  const tabChosen = useRef(Boolean(initialTab));
  function setTab(next: DetailTab) {
    tabChosen.current = true;
    setTabState(next);
    onTabChange?.(next);
  }
  const [activeFinding, setActiveFinding] = useState<ImagingFinding | null>(null);
  // The section whose wording is outlined in the viewer.
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const [boundaryLines, setBoundaryLines] = useState<ReportLineItem[] | null>(null);
  const [linesAdjustable, setLinesAdjustable] = useState(false);
  const pageCount = study.report_page_count ?? null;
  const active = sections.find((section) => section.section_type === activeSection) || null;
  const pageRegions = (active?.source_regions || []).filter((region) => region.page === selectedPage);
  let viewerNote = "";
  if (active) {
    const label = SECTION_LABELS[active.section_type] || active.section_type;
    const end = active.page_end || active.page_number;
    if (selectedPage < active.page_number || selectedPage > end) {
      viewerNote = `${label} is on page ${active.page_number}${end > active.page_number ? `–${end}` : ""}.`;
    } else if (pageRegions.length) {
      viewerNote = `Outlined: the ${label} wording on this page.`;
    } else {
      viewerNote = `No position was recorded for ${label}. Read it on the page yourself.`;
    }
  }

  // Whether this report can have its boundaries adjusted (it was read
  // with line positions). Asked once per report.
  useEffect(() => {
    let cancelled = false;
    if (!study.report_document_id) return;
    void onLoadLines().then((data) => {
      if (!cancelled) setLinesAdjustable(Boolean(data?.adjustable && data.lines.length));
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [study.report_document_id]);

  useEffect(() => {
    if (study.verification_status === "verified" && canShowOverview && !tabChosen.current) {
      // Not recorded in the URL: a refresh repeats this same default.
      setTabState("overview");
    }
  }, [study.verification_status, canShowOverview]);

  const title =
    study.study_description?.trim() ||
    [MODALITY_LABELS[study.modality], study.body_region].filter(Boolean).join(" · ") ||
    MODALITY_LABELS[study.modality];

  function viewSourcePage(pageNumber: number, documentId?: string, sectionType?: string) {
    if (sectionType !== undefined) setActiveSection(sectionType);
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

      <PageHero
        className="imaging-study-meta"
        eyebrow={`Imaging · ${MODALITY_LABELS[study.modality]}`}
        title={title}
        lead={`${formatStudyDate(study.study_date)}${study.institution ? ` · ${study.institution}` : ""}`}
        meta={<ImagingStatusChip state={state} />}
        actions={<>
          <button type="button" className="quiet-button" onClick={onOpenHistory}>
            <History size={14} /> View history
          </button>
          <button type="button" className="quiet-button" onClick={onOpenCompare}>
            <GitCompare size={14} /> Compare
          </button>
          <button type="button" className="quiet-button imaging-delete" onClick={onRequestDelete}>
            <Trash2 size={14} /> Delete study
          </button>
        </>}
      />

      <p className="imaging-boundary imaging-image-boundary">
        <ScanLine size={14} aria-hidden="true" /> MediGuide explains the radiologist&apos;s report. It does not independently diagnose the scan.
      </p>

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
              <ImagingPageViewer
                src={previewUrl}
                page={selectedPage}
                pageCount={pageCount}
                onPage={setSelectedPage}
                regions={pageRegions}
                note={viewerNote}
                extraControls={
                  <button type="button" className="quiet-button" aria-label="Expand" onClick={() => setViewerExpanded(true)}>
                    <Maximize2 size={14} />
                  </button>
                }
              />
              <div className="imaging-report-stack">
                <ImagingReportDetails study={study} applying={applyingDetails} onApply={onApplyDetails} />
                {boundaryLines ? (
                  <ImagingBoundaryEditor
                    lines={boundaryLines}
                    sections={sections}
                    saving={savingBoundaries}
                    onCancel={() => setBoundaryLines(null)}
                    onSave={(ranges) => {
                      void onSaveBoundaries(ranges).then((ok) => { if (ok) setBoundaryLines(null); });
                    }}
                  />
                ) : (
                  <ImagingReportPanel
                    study={study}
                    sections={sections}
                    busySection={busySection}
                    activeSection={activeSection}
                    onDecide={onDecideSection}
                    onSelectSection={(section) => {
                      setActiveSection(section.section_type);
                      setSelectedPage(section.page_number);
                    }}
                    onViewSourcePage={(section) => viewSourcePage(section.page_number, undefined, section.section_type)}
                    onOpenTerminology={onOpenTerminology}
                    canAdjustBoundaries={linesAdjustable}
                    onAdjustBoundaries={() => {
                      void onLoadLines().then((data) => { if (data?.lines.length) setBoundaryLines(data.lines); });
                    }}
                  />
                )}
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
              <ImagingPageViewer
                className="imaging-viewer-full"
                src={previewUrl}
                page={selectedPage}
                pageCount={pageCount}
                onPage={setSelectedPage}
                regions={tab === "source" ? pageRegions : []}
                note={tab === "source" ? viewerNote : ""}
              />
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
