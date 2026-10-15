"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Check, ChevronDown, FileText, FlaskConical, Pill, ScanLine, X } from "lucide-react";
import { fetchWithTimeout } from "../../lib/api-error";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import { usePaginatedTimeline } from "../../lib/usePaginatedTimeline";
import { Button, EmptyState, Input, ServiceError } from "./polish-ui";
import { PageHero } from "./_components/PageHero";
import { SourceEvidence, type SourceEvidenceOpenPayload } from "./_components/SourceEvidence";
import type { TimelineCategory, TimelineEntry, TimelineFilters } from "./_state/timeline-types";

interface MedicationRecord {
  medication_id: string;
  medication_name: string;
  strength: string;
  form: string;
  instructions: string;
  quantity: string;
  prescriber_or_pharmacy: string;
  source: "upload" | "typed";
  other_visible_text: string;
}

const CATEGORY_ICONS: Record<TimelineCategory, typeof ScanLine> = {
  imaging: ScanLine,
  laboratory: FlaskConical,
  medication: Pill,
  document: FileText,
};

const CATEGORY_LABELS: Record<TimelineCategory, string> = {
  imaging: "Imaging",
  laboratory: "Laboratory",
  medication: "Medication",
  document: "Document",
};

const ACTION_LABELS: Record<TimelineCategory, string> = {
  imaging: "View study",
  laboratory: "View results",
  medication: "View medication",
  document: "View document",
};

const FILTER_TABS: { key: TimelineCategory | ""; label: string }[] = [
  { key: "", label: "All" },
  { key: "laboratory", label: "Labs" },
  { key: "imaging", label: "Imaging" },
  { key: "medication", label: "Medications" },
  { key: "document", label: "Documents" },
];

function formatEntryDate(value: string | null): string {
  if (!value) return "Undated";
  try {
    return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
      month: "short",
      day: "2-digit",
    }).toUpperCase();
  } catch {
    return value;
  }
}

export function HealthTimeline({
  apiUrl,
  onOpenDocument,
  onOpenImagingStudy,
}: {
  apiUrl: string;
  onOpenDocument: (documentId: string, pageNumber?: number, fieldId?: string) => void;
  onOpenImagingStudy: (studyId: string) => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [typeFilter, setTypeFilter] = useState<TimelineCategory | "">(
    () => (searchParams.get("type") as TimelineCategory | null) || ""
  );
  const [dateFrom, setDateFrom] = useState(() => searchParams.get("from") || "");
  const [dateTo, setDateTo] = useState(() => searchParams.get("to") || "");
  const [searchInput, setSearchInput] = useState(() => searchParams.get("q") || "");
  const debouncedSearch = useDebouncedValue(searchInput, 300);

  // Mirror filter state into the URL so a filtered view is bookmarkable/
  // shareable and survives a refresh — same query-param-for-view-state
  // precedent as the existing `?openStudy=` pattern.
  useEffect(() => {
    const params = new URLSearchParams();
    if (typeFilter) params.set("type", typeFilter);
    if (dateFrom) params.set("from", dateFrom);
    if (dateTo) params.set("to", dateTo);
    if (debouncedSearch) params.set("q", debouncedSearch);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typeFilter, dateFrom, dateTo, debouncedSearch]);

  const filters: TimelineFilters = useMemo(
    () => ({
      eventType: typeFilter || undefined,
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
      search: debouncedSearch || undefined,
    }),
    [typeFilter, dateFrom, dateTo, debouncedSearch],
  );

  // Page size is overridable via NEXT_PUBLIC_TIMELINE_PAGE_SIZE (same
  // test-only-tunable pattern as playwright.config.ts's OLLAMA_TIMEOUT_SECONDS)
  // so E2E can exercise "Load more" without seeding 25+ records through the UI.
  const pageSize = Number(process.env.NEXT_PUBLIC_TIMELINE_PAGE_SIZE) || 25;
  const { entries, hasMore, totalMatched, status, error, loadMore, reload } =
    usePaginatedTimeline(apiUrl, filters, pageSize);

  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  function toggleExpanded(entryId: string) {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(entryId)) next.delete(entryId);
      else next.add(entryId);
      return next;
    });
  }

  const [medicationDrawerId, setMedicationDrawerId] = useState<string | null>(null);
  const [medicationRecord, setMedicationRecord] = useState<MedicationRecord | null>(null);
  const [medicationLoading, setMedicationLoading] = useState(false);
  const [medicationError, setMedicationError] = useState("");

  async function openMedicationDrawer(medicationId: string) {
    setMedicationDrawerId(medicationId);
    setMedicationRecord(null);
    setMedicationLoading(true);
    try {
      const response = await fetchWithTimeout(`${apiUrl}/api/medications/v2/${medicationId}/record`);
      if (!response.ok) throw new Error("Could not load this medication record.");
      setMedicationRecord(await response.json());
    } catch (err) {
      setMedicationError(err instanceof Error ? err.message : "Could not load this medication record.");
      setMedicationDrawerId(null);
    } finally {
      setMedicationLoading(false);
    }
  }

  // Only ever called from the per-measurement SourceEvidence below (always
  // type="laboratory", always carries a documentId) — the entry-level
  // action still goes through handleEntryAction, which already dispatches
  // correctly per category via the existing onOpenDocument/onOpenImagingStudy
  // props.
  function handleSourceOpen(evidence: SourceEvidenceOpenPayload) {
    if (evidence.documentId) {
      onOpenDocument(evidence.documentId, evidence.pageNumber ?? undefined, evidence.fieldId ?? undefined);
    }
  }

  function handleEntryAction(entry: TimelineEntry) {
    if (entry.link.type === "imaging_study") onOpenImagingStudy(entry.link.id);
    else if (entry.link.type === "document") onOpenDocument(entry.link.id, entry.page_number ?? undefined);
    else if (entry.link.type === "medication") void openMedicationDrawer(entry.link.id);
  }

  const byYear = new Map<string, TimelineEntry[]>();
  for (const entry of entries) {
    const year = entry.date ? entry.date.slice(0, 4) : "Undated";
    byYear.set(year, [...(byYear.get(year) || []), entry]);
  }
  const years = [...byYear.keys()].sort((a, b) => b.localeCompare(a));

  const hasActiveFilters = Boolean(typeFilter || dateFrom || dateTo || searchInput);
  function clearFilters() {
    setTypeFilter("");
    setDateFrom("");
    setDateTo("");
    setSearchInput("");
  }

  return (
    <div className="workflow-view timeline-view">
      <PageHero
        eyebrow="Health timeline"
       
        title="Health Timeline"
        lead="See verified information across your health records in one chronological view. Every entry links back to its original source."
      />

      <div className="timeline-filter-bar" role="group" aria-label="Filter timeline">
        <div className="timeline-filter-tabs" role="tablist" aria-label="Record type">
          {FILTER_TABS.map((tab) => (
            <button
              key={tab.key || "all"}
              type="button"
              role="tab"
              aria-selected={typeFilter === tab.key}
              className={typeFilter === tab.key ? "ui-tab active" : "ui-tab"}
              onClick={() => setTypeFilter(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="timeline-filter-fields">
          <label className="timeline-filter-date">
            <span>From</span>
            <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} aria-label="Filter from date" />
          </label>
          <label className="timeline-filter-date">
            <span>To</span>
            <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} aria-label="Filter to date" />
          </label>
          <Input
            className="timeline-filter-search"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search timeline"
            aria-label="Search timeline"
          />
          {hasActiveFilters && (
            <Button onClick={clearFilters}>Clear filters</Button>
          )}
        </div>
      </div>

      {status === "error" && (
        <ServiceError
          title="We couldn't load your health timeline"
          message={`${error} Your records are still available.`}
          onRetry={reload}
        />
      )}

      {status === "loading" && entries.length === 0 ? (
        <div className="load-state-loading" role="status" aria-live="polite" aria-label="Loading timeline">
          <span className="load-skeleton" />
          <span className="load-skeleton" />
          <span className="load-skeleton short" />
        </div>
      ) : status !== "error" && entries.length === 0 ? (
        hasActiveFilters ? (
          <EmptyState title="No events match these filters" body="Try a different date range, type, or search term.">
            <Button onClick={clearFilters}>Clear filters</Button>
          </EmptyState>
        ) : (
          <EmptyState
            title="No health history yet"
            body="Upload a document, add imaging, or enter medication information to start building your health timeline."
          >
            <Button variant="primary" onClick={() => router.push("/workspace/documents?action=upload")}>Upload document</Button>
            <Button onClick={() => router.push("/workspace/documents?action=sample")}>Try synthetic data</Button>
          </EmptyState>
        )
      ) : (
        <>
          {years.map((year) => (
            <div key={year} className="imaging-history-year">
              <h3>{year}</h3>
              <ol className="timeline-entries">
                {(byYear.get(year) || []).map((entry) => {
                  const Icon = CATEGORY_ICONS[entry.event_type] ?? FileText;
                  const isLab = entry.category === "laboratory";
                  const expanded = expandedIds.has(entry.entry_id);
                  return (
                    <li key={entry.entry_id} className="timeline-entry">
                      <div className="timeline-entry-date">
                        {formatEntryDate(entry.date)}
                        {entry.date && entry.date_label && <span className="timeline-entry-date-label">{entry.date_label}</span>}
                      </div>
                      <div className="timeline-entry-body">
                        <div className="timeline-entry-category">
                          <Icon size={14} aria-hidden="true" /> {CATEGORY_LABELS[entry.category]}
                        </div>
                        <strong>{entry.title}</strong>
                        {entry.subtitle && <p className="timeline-entry-subtitle">{entry.subtitle}</p>}
                        <span className="lab-verified">
                          <Check size={13} /> {entry.verification_label}
                        </span>
                        {isLab && entry.measurements && entry.measurements.length > 0 && (
                          <>
                            <button
                              type="button"
                              className="quiet-button timeline-expand-toggle"
                              aria-expanded={expanded}
                              onClick={() => toggleExpanded(entry.entry_id)}
                            >
                              <ChevronDown size={14} className={expanded ? "timeline-expand-icon open" : "timeline-expand-icon"} />
                              {expanded ? "Hide measurements" : `Show ${entry.measurements.length} measurement${entry.measurements.length === 1 ? "" : "s"}`}
                            </button>
                            {expanded && (
                              <ul className="timeline-measurements">
                                {entry.measurements.map((measurement) => (
                                  <li key={measurement.field_id} className="timeline-measurement-row">
                                    <span className="timeline-measurement-name">{measurement.test_name}</span>
                                    <span className="timeline-measurement-value">
                                      {measurement.value_text}{measurement.unit ? ` ${measurement.unit}` : ""}
                                    </span>
                                    <SourceEvidence
                                      type="laboratory"
                                      title={measurement.test_name}
                                      documentId={entry.document_id}
                                      pageNumber={measurement.page_number}
                                      fieldId={measurement.field_id}
                                      verificationStatus="verified"
                                      route={`/workspace/documents/${entry.document_id}?page=${measurement.page_number}&field=${measurement.field_id}`}
                                      compact
                                      onOpen={handleSourceOpen}
                                    />
                                  </li>
                                ))}
                              </ul>
                            )}
                          </>
                        )}
                      </div>
                      <button type="button" className="quiet-button timeline-entry-action" onClick={() => handleEntryAction(entry)}>
                        {ACTION_LABELS[entry.category]}
                      </button>
                    </li>
                  );
                })}
              </ol>
            </div>
          ))}
          {hasMore && (
            <div className="timeline-load-more">
              <Button onClick={loadMore}>
                {status === "loading" ? "Loading…" : `Load more (${entries.length} of ${totalMatched})`}
              </Button>
            </div>
          )}
        </>
      )}

      {medicationError && (
        <div className="service-error" role="alert">
          <div>
            <strong>Something needs attention</strong>
            <p>{medicationError}</p>
          </div>
          <button type="button" className="quiet-button" onClick={() => setMedicationError("")}>
            <X size={14} /> Dismiss
          </button>
        </div>
      )}

      <MedicationDrawer
        open={medicationDrawerId !== null}
        record={medicationRecord}
        loading={medicationLoading}
        onClose={() => setMedicationDrawerId(null)}
      />
    </div>
  );
}

function MedicationDrawer({
  open,
  record,
  loading,
  onClose,
}: {
  open: boolean;
  record: MedicationRecord | null;
  loading: boolean;
  onClose: () => void;
}) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previouslyFocused.current?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="drawer-backdrop" onClick={onClose} role="presentation">
      <div className="drawer" role="dialog" aria-modal="true" aria-labelledby={titleId} onClick={(event) => event.stopPropagation()}>
        <button ref={closeRef} type="button" className="drawer-close" aria-label="Close" onClick={onClose}>
          <X size={18} />
        </button>
        <h2 id={titleId}>Medication</h2>
        {loading && <p className="imaging-empty-note">Loading...</p>}
        {record && (
          <>
            <div className="imaging-original-extraction">
              <small>Medication name</small>
              <p>{record.medication_name || "Not recorded"}</p>
            </div>
            {record.strength && (
              <div className="imaging-original-extraction">
                <small>Strength</small>
                <p>{record.strength}</p>
              </div>
            )}
            {record.form && (
              <div className="imaging-original-extraction">
                <small>Form</small>
                <p>{record.form}</p>
              </div>
            )}
            {record.instructions && (
              <div className="imaging-original-extraction">
                <small>Directions for use</small>
                <p>{record.instructions}</p>
              </div>
            )}
            {record.quantity && (
              <div className="imaging-original-extraction">
                <small>Quantity / refills</small>
                <p>{record.quantity}</p>
              </div>
            )}
            {record.prescriber_or_pharmacy && (
              <div className="imaging-original-extraction">
                <small>Prescriber or pharmacy</small>
                <p>{record.prescriber_or_pharmacy}</p>
              </div>
            )}
            <p className="imaging-note">
              This is the information you confirmed at the time. The original label image is not
              kept long-term, so it isn&rsquo;t shown here.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
