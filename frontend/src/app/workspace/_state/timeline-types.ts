// Shared TimelineEvent vocabulary — used by Home, HealthTimeline, and the
// Cmd/Ctrl+K command palette / SourceEvidence, so there's one definition of
// what a timeline entry looks like instead of three drifting copies.

export type TimelineCategory = "imaging" | "laboratory" | "medication" | "document";

export interface TimelineLink {
  type: "imaging_study" | "document" | "medication";
  id: string;
}

export interface TimelineMeasurement {
  test_code: string;
  test_name: string;
  value_text: string;
  value_numeric: number | null;
  unit: string;
  range_status: string;
  page_number: number;
  field_id: string;
}

export interface TimelineEntry {
  entry_id: string;
  date: string | null;
  /** What the date is: "Collected", "Report date", "Study date", "Added to MediGuide". */
  date_label?: string | null;
  category: TimelineCategory;
  title: string;
  subtitle: string;
  verification_label: string;
  verified: boolean;
  link: TimelineLink;
  // Additive Phase 2 fields — see src/database/timeline_repository.py.
  event_type: TimelineCategory;
  source_type: string;
  source_id: string;
  document_id: string | null;
  page_number: number | null;
  route: string;
  is_demo: boolean;
  measurements: TimelineMeasurement[] | null;
}

export interface TimelineResponse {
  entries: TimelineEntry[];
  next_cursor: string | null;
  total_matched: number;
}

export interface TimelineFilters {
  eventType?: TimelineCategory;
  dateFrom?: string;
  dateTo?: string;
  search?: string;
}
