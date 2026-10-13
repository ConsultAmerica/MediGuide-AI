"use client";

import { useCallback } from "react";
import Link from "next/link";
import { FileText, ImageIcon, Pill, ScanLine, ShieldCheck, Stethoscope } from "lucide-react";
import { useAsyncData } from "../../../lib/useAsyncData";
import { Button, LoadState, MetricCard } from "../polish-ui";
import { useWorkspaceContext } from "../_state/WorkspaceStateProvider";
import { API_URL, type DocSession, type LabPoint } from "../_state/workspace-shared";
import type { TimelineCategory, TimelineEntry } from "../_state/timeline-types";
import { apiFetch } from "../../../lib/auth";

type ImagingStudySummary = { study_id: string; modality: string; body_region: string; study_date: string | null; verification_status: string };

const CATEGORY_LABELS: Record<TimelineCategory, string> = {
  imaging: "IMAGING",
  laboratory: "LAB",
  medication: "MEDICATION",
  document: "DOCUMENT",
};

async function fetchJson<T>(path: string, key: string): Promise<T[]> {
  const response = await apiFetch(`${API_URL}${path}`);
  if (!response.ok) throw new Error(`Could not load ${key}.`);
  const data = await response.json();
  return data[key] || [];
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function HomePage() {
  const { router, inspectDocument } = useWorkspaceContext();

  const documentsState = useAsyncData(useCallback(() => fetchJson<DocSession>("/api/documents/v2/sessions", "sessions"), []));
  const labsState = useAsyncData(useCallback(() => fetchJson<LabPoint>("/api/labs/summary", "points"), []));
  const imagingState = useAsyncData(useCallback(() => fetchJson<ImagingStudySummary>("/api/imaging/studies", "studies"), []));
  const timelineState = useAsyncData(useCallback(() => fetchJson<TimelineEntry>("/api/timeline?limit=5", "entries"), []));

  const needsReviewDocs = documentsState.status === "ready" ? documentsState.data.filter((doc) => !doc.confirmed) : [];
  const needsReviewImaging = imagingState.status === "ready" ? imagingState.data.filter((study) => study.verification_status !== "verified") : [];
  const hasReviewData = documentsState.status === "ready" && imagingState.status === "ready";
  const needsReviewCount = needsReviewDocs.length + needsReviewImaging.length;

  function openTimelineEntry(entry: TimelineEntry) {
    if (entry.link.type === "document") void inspectDocument(entry.link.id, entry.page_number || 1);
    else if (entry.link.type === "imaging_study") router.push(`/workspace/imaging/${entry.link.id}`);
    else router.push("/workspace/timeline");
  }

  return (
    <div className="workflow-view home-view">
      <div className="workflow-heading-row">
        <div>
          <p className="eyebrow">HOME</p>
          <h2>{greeting()}.</h2>
          <p className="workflow-lead">Your health information.</p>
        </div>
      </div>

      <div className="metric-card-grid">
        <LoadState state={documentsState} onRetry={documentsState.reload} errorTitle="Could not load documents">
          {(sessions) => <MetricCard label="Recent documents" value={sessions.length} icon={FileText} href="/workspace/documents" />}
        </LoadState>
        <LoadState state={labsState} onRetry={labsState.reload} errorTitle="Could not load labs">
          {(points) => <MetricCard label="Verified results" value={points.length} icon={ShieldCheck} href="/workspace/labs" />}
        </LoadState>
        <LoadState state={imagingState} onRetry={imagingState.reload} errorTitle="Could not load imaging">
          {(studies) => <MetricCard label="Imaging studies" value={studies.length} icon={ScanLine} href="/workspace/imaging" />}
        </LoadState>
      </div>

      <section className="home-section">
        <p className="eyebrow">NEEDS YOUR REVIEW</p>
        {!hasReviewData ? (
          <div className="load-state-loading" role="status" aria-live="polite" aria-label="Loading">
            <span className="load-skeleton" /><span className="load-skeleton short" />
          </div>
        ) : needsReviewCount === 0 ? (
          <p className="workflow-lead">Nothing needs your review right now.</p>
        ) : (
          <div className="needs-review-list">
            {needsReviewDocs.map((doc) => (
              <div key={doc.document_id} className="needs-review-row">
                <FileText size={16} />
                <div><strong>{doc.filename}</strong><small>{doc.field_count} measurement{doc.field_count === 1 ? "" : "s"} need review</small></div>
                <Button onClick={() => void inspectDocument(doc.document_id, 1)}>Review →</Button>
              </div>
            ))}
            {needsReviewImaging.map((study) => (
              <div key={study.study_id} className="needs-review-row">
                <ScanLine size={16} />
                <div><strong>{study.modality} · {study.body_region || "Imaging study"}</strong><small>Report needs review</small></div>
                <Button onClick={() => router.push(`/workspace/imaging/${study.study_id}`)}>Review →</Button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="home-section">
        <div className="home-section-heading">
          <p className="eyebrow">RECENT HISTORY</p>
          <Link href="/workspace/timeline" className="quiet-button">View all</Link>
        </div>
        <LoadState
          state={timelineState}
          onRetry={timelineState.reload}
          errorTitle="Could not load your history"
          isEmpty={(entries) => entries.length === 0}
          emptyTitle="No history yet"
          emptyBody="Documents, labs, imaging, and medications appear here once verified."
        >
          {(entries) => (
            <div className="recent-history-list">
              {entries.map((entry) => (
                <button key={entry.entry_id} type="button" className="recent-history-row" onClick={() => openTimelineEntry(entry)}>
                  <span className="recent-history-date">{entry.date || "Undated"}</span>
                  <span className="recent-history-body">
                    <small className="recent-history-category">{CATEGORY_LABELS[entry.category]}</small>
                    <strong>{entry.title}</strong>
                    <small>{entry.subtitle}</small>
                  </span>
                </button>
              ))}
            </div>
          )}
        </LoadState>
      </section>

      <section className="home-section">
        <p className="eyebrow">QUICK ACTIONS</p>
        <div className="quick-action-row">
          <Button variant="primary" icon={FileText} onClick={() => router.push("/workspace/documents?action=upload")}>Upload document</Button>
          <Button icon={ImageIcon} onClick={() => router.push("/workspace/imaging")}>Add imaging</Button>
          <Button icon={Pill} onClick={() => router.push("/workspace/medications?action=upload")}>Add medication</Button>
          <Button icon={Stethoscope} onClick={() => router.push("/workspace/visit")}>Prepare for visit</Button>
        </div>
      </section>
    </div>
  );
}
