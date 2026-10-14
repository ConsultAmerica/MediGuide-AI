"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { FileText, ImageIcon, Milestone, Pill, Search, Stethoscope } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { fetchWithTimeout, parseApiError } from "../../../lib/api-error";
import { useDebouncedValue } from "../../../lib/useDebouncedValue";
import { useWorkspaceContext } from "../_state/WorkspaceStateProvider";
import { API_URL } from "../_state/workspace-shared";
import type { SourceEvidenceType } from "./SourceEvidence";

interface SearchResult {
  result_id: string;
  type: SourceEvidenceType;
  title: string;
  subtitle: string;
  date: string | null;
  document_id: string | null;
  page_number: number | null;
  /** The lab value the query matched, so the hit opens with it highlighted. */
  field_id?: string | null;
  verification_status: string;
  route: string;
}

type PaletteItem =
  | { kind: "command"; key: string; label: string; icon: LucideIcon; route: string }
  | { kind: "result"; result: SearchResult };

const QUICK_COMMANDS: { key: string; label: string; icon: LucideIcon; route: string }[] = [
  { key: "upload-document", label: "Upload document", icon: FileText, route: "/workspace/documents?action=upload" },
  { key: "upload-imaging", label: "Upload imaging", icon: ImageIcon, route: "/workspace/imaging" },
  { key: "add-medication", label: "Add medication", icon: Pill, route: "/workspace/medications?action=upload" },
  { key: "open-timeline", label: "Open Health Timeline", icon: Milestone, route: "/workspace/timeline" },
  { key: "prepare-visit", label: "Prepare for visit", icon: Stethoscope, route: "/workspace/visit" },
];

// "imaging" (the study itself) and "imaging_section" (one of its confirmed
// report sections) render as one "IMAGING" group, not two side-by-side
// sections with the same visible heading — a single search hit set can
// legitimately contain both (e.g. the study title and its Exam section both
// match the same query).
const RESULT_GROUP_KEYS: Record<string, string> = {
  laboratory: "laboratory",
  document: "document",
  imaging: "imaging",
  imaging_section: "imaging",
  medication: "medication",
};

const RESULT_GROUP_LABELS: Record<string, string> = {
  laboratory: "LAB RESULTS",
  document: "DOCUMENTS",
  imaging: "IMAGING",
  medication: "MEDICATIONS",
};

const RESULT_GROUP_ORDER = ["laboratory", "imaging", "document", "medication"];

function groupResults(results: SearchResult[]): { key: string; label: string; items: SearchResult[] }[] {
  const byGroup = new Map<string, SearchResult[]>();
  for (const result of results) {
    const key = RESULT_GROUP_KEYS[result.type] || result.type;
    byGroup.set(key, [...(byGroup.get(key) || []), result]);
  }
  return RESULT_GROUP_ORDER.filter((key) => byGroup.has(key)).map((key) => ({
    key,
    label: RESULT_GROUP_LABELS[key] || key.toUpperCase(),
    items: byGroup.get(key) || [],
  }));
}

export function CommandPalette({ onClose }: { onClose: () => void }) {
  const { router, inspectDocument } = useWorkspaceContext();
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query, 250);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "ready">("idle");
  const [error, setError] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  // Bumped by "Try again" so the same query is fetched once more.
  const [attempt, setAttempt] = useState(0);

  const titleId = useId();
  const listboxId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const latestQueryRef = useRef("");

  const isSearching = query.trim().length >= 2;

  // Focus the input on open, restore whatever had focus before Cmd/Ctrl+K
  // was pressed on close/unmount — same pattern as the existing Drawer/
  // MedicationDrawer primitives.
  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();
    return () => {
      previouslyFocused.current?.focus();
    };
  }, []);

  useEffect(() => {
    // Fetch-on-debounced-query-change from the backend (an external
    // system) — the synchronous setState calls below reset local UI state
    // for that fetch, not derive it from render, so this is the same
    // intentional pattern as WorkspaceStateProvider's localStorage-hydration
    // effect.
    /* eslint-disable react-hooks/set-state-in-effect */
    const trimmed = debouncedQuery.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setStatus("idle");
      return;
    }
    // fetchWithTimeout (frontend/src/lib/api-error.ts) builds its own
    // internal AbortController and would silently discard any `signal` we
    // passed in, so true request cancellation isn't available here — this
    // "latest query wins" guard achieves the same practical effect (a
    // slower earlier keystroke's response can never overwrite a newer
    // one's), it just doesn't stop the superseded request server-side.
    latestQueryRef.current = trimmed;
    setStatus("loading");
    setError("");
    /* eslint-enable react-hooks/set-state-in-effect */
    void (async () => {
      try {
        const response = await fetchWithTimeout(`${API_URL}/api/search?q=${encodeURIComponent(trimmed)}`);
        if (!response.ok) {
          const apiError = await parseApiError(response, "Search is temporarily unavailable.");
          throw new Error(apiError.message);
        }
        const data = await response.json();
        if (latestQueryRef.current !== trimmed) return;
        setResults(data.results || []);
        setStatus("ready");
        setActiveIndex(0);
      } catch (err) {
        if (latestQueryRef.current !== trimmed) return;
        setError(err instanceof Error ? err.message : "Search is temporarily unavailable.");
        setStatus("error");
      }
    })();
  }, [debouncedQuery, attempt]);

  const groups = useMemo(() => (isSearching ? groupResults(results) : null), [isSearching, results]);

  // Built from the grouped order the list renders in, so the highlighted
  // option and the one Enter opens are always the same result.
  const items: PaletteItem[] = useMemo(() => {
    if (!groups) {
      return QUICK_COMMANDS.map((command) => ({ kind: "command" as const, ...command }));
    }
    return groups.flatMap((group) => group.items.map((result) => ({ kind: "result" as const, result })));
  }, [groups]);

  function openItem(item: PaletteItem) {
    if (item.kind === "command") {
      router.push(item.route);
      onClose();
      return;
    }
    const { result } = item;
    if ((result.type === "laboratory" || result.type === "document") && result.document_id) {
      void inspectDocument(result.document_id, result.page_number ?? 1, result.field_id ?? undefined);
    } else {
      router.push(result.route);
    }
    onClose();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => Math.min(current + 1, Math.max(items.length - 1, 0)));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => Math.max(current - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const item = items[activeIndex];
      if (item) openItem(item);
      return;
    }
    if (event.key === "Tab") {
      // Only the search input is a real tab stop in this dialog — results
      // are selected via Arrow keys/Enter (a roving "virtual focus" via
      // aria-activedescendant, not real DOM focus moves), so trapping Tab
      // here just means "never let it leave the dialog."
      event.preventDefault();
    }
  }

  let flatIndex = -1;

  return (
    <div className="drawer-backdrop command-palette-backdrop" onClick={onClose} role="presentation">
      <div
        className="command-palette"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <h2 id={titleId} className="command-palette-title">Search MediGuide</h2>
        <div className="command-palette-input-row">
          <Search size={16} aria-hidden="true" />
          <input
            ref={inputRef}
            role="combobox"
            aria-expanded={items.length > 0}
            aria-controls={listboxId}
            aria-autocomplete="list"
            aria-activedescendant={items[activeIndex] ? `command-palette-item-${activeIndex}` : undefined}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search your health information..."
            aria-label="Search your health information"
            className="command-palette-input"
          />
        </div>

        <div
          id={listboxId}
          role="listbox"
          aria-label={isSearching ? "Search results" : "Quick commands"}
          className="command-palette-results"
        >
          {status === "loading" && <p className="command-palette-status">Searching…</p>}
          {status === "error" && (
            <div className="command-palette-status">
              <p>{error}</p>
              <button type="button" className="quiet-button" onClick={() => setAttempt((value) => value + 1)}>Try again</button>
            </div>
          )}
          {isSearching && status === "ready" && results.length === 0 && (
            <p className="command-palette-status">
              No results for &ldquo;{query.trim()}&rdquo;. Try another term or search your documents by name.
            </p>
          )}
          {/* Announced to screen readers on every result-count change. */}
          <p className="sr-only" role="status" aria-live="polite">
            {isSearching && status === "ready" ? `${results.length} result${results.length === 1 ? "" : "s"} found` : ""}
          </p>

          {!isSearching &&
            QUICK_COMMANDS.map((command) => {
              flatIndex += 1;
              const currentIndex = flatIndex;
              const Icon = command.icon;
              return (
                <button
                  key={command.key}
                  id={`command-palette-item-${currentIndex}`}
                  type="button"
                  role="option"
                  aria-selected={currentIndex === activeIndex}
                  className={currentIndex === activeIndex ? "command-palette-item active" : "command-palette-item"}
                  onMouseEnter={() => setActiveIndex(currentIndex)}
                  onClick={() => openItem({ kind: "command", ...command })}
                >
                  <Icon size={16} />
                  <span>{command.label}</span>
                </button>
              );
            })}

          {isSearching &&
            groups?.map((group) => (
              <div key={group.key} className="command-palette-group">
                <p className="command-palette-group-label">{group.label}</p>
                {group.items.map((result) => {
                  flatIndex += 1;
                  const currentIndex = flatIndex;
                  return (
                    <button
                      key={result.result_id}
                      id={`command-palette-item-${currentIndex}`}
                      type="button"
                      role="option"
                      aria-selected={currentIndex === activeIndex}
                      className={currentIndex === activeIndex ? "command-palette-item active" : "command-palette-item"}
                      onMouseEnter={() => setActiveIndex(currentIndex)}
                      onClick={() => openItem({ kind: "result", result })}
                    >
                      <span className="command-palette-item-body">
                        <strong>{result.title}</strong>
                        {result.subtitle && <small>{result.subtitle}</small>}
                      </span>
                    </button>
                  );
                })}
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
