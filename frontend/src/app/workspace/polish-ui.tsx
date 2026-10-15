"use client";

import { useEffect, useId, useRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";
import Link from "next/link";
import { Activity, Check, Circle, RefreshCw, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { AsyncDataState } from "../../lib/useAsyncData";

export type ToastTone = "success" | "info" | "error";

export type ToastItem = {
  id: string;
  message: string;
  tone: ToastTone;
};

export function ToastStack({
  toasts,
  onDismiss,
}: {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}) {
  if (!toasts.length) return null;
  return (
    <div className="toast-stack" aria-live="polite" aria-relevant="additions">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast-item toast-${toast.tone}`} role="status">
          <span>{toast.message}</span>
          <button type="button" className="toast-dismiss" aria-label="Dismiss" onClick={() => onDismiss(toast.id)}>
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  const confirmRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    confirmRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previouslyFocused.current?.focus();
    };
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="drawer-backdrop confirm-backdrop" onClick={onCancel} role="presentation">
      <div
        className="confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id={titleId}>{title}</h2>
        <p>{body}</p>
        <div className="confirm-dialog-actions">
          <button type="button" className="quiet-button" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            className={destructive ? "forest-button destructive-confirm" : "forest-button"}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export type ProcessStageId = "upload" | "validate" | "read" | "extract" | "review";

const PROCESS_STAGES: { id: ProcessStageId; label: string }[] = [
  { id: "upload", label: "Upload complete" },
  { id: "validate", label: "File validated" },
  { id: "read", label: "Reading document" },
  { id: "extract", label: "Extracting information" },
  { id: "review", label: "Preparing review" },
];

export function ProcessingChecklist({
  activeStage,
  failed = false,
  title = "Processing your document",
  waitingMessage,
  attempt,
  maxAttempts,
}: {
  activeStage: ProcessStageId | null;
  failed?: boolean;
  title?: string;
  /** Overrides the current stage's label (e.g. "Document processing is
   * starting up.") while an automatic retry is in flight, without
   * changing the fixed stage list/order underneath it. */
  waitingMessage?: string;
  attempt?: number;
  maxAttempts?: number;
}) {
  if (!activeStage) return null;
  const order = PROCESS_STAGES.map((stage) => stage.id);
  const activeIndex = order.indexOf(activeStage);

  return (
    <div className="process-checklist" role="status" aria-live="polite">
      <strong>{failed ? "We couldn't finish reading this document." : title}</strong>
      <ol>
        {PROCESS_STAGES.map((stage, index) => {
          const done = !failed && index < activeIndex;
          const current = index === activeIndex;
          return (
            <li key={stage.id} className={done ? "done" : current ? (failed ? "failed" : "current") : "pending"}>
              {done ? <Check size={14} /> : current && failed ? <X size={14} /> : <Circle size={14} />}
              <span>{current && waitingMessage ? waitingMessage : stage.label}</span>
            </li>
          );
        })}
      </ol>
      {!failed && attempt && maxAttempts ? (
        <small className="process-checklist-attempt">Attempt {attempt} of {maxAttempts}</small>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty-state-panel">
      <strong>{title}</strong>
      <p>{body}</p>
      {children ? <div className="empty-state-actions">{children}</div> : null}
    </div>
  );
}

export function mapStatusToProcessStage(status: string, loading: string): ProcessStageId | null {
  const lower = `${status} ${loading}`.toLowerCase();
  if (!loading && !status) return null;
  if (lower.includes("upload")) return "upload";
  if (lower.includes("valid") || lower.includes("preparing page") || lower.includes("queued")) return "validate";
  if (lower.includes("render") || lower.includes("reading") || lower.includes("scanned")) return "read";
  if (lower.includes("extract")) return "extract";
  if (lower.includes("review") || lower.includes("complete")) return "review";
  if (loading) return "read";
  return null;
}

export const FRIENDLY_HEALTH_LABELS: Record<string, string> = {
  fastapi: "Document processing",
  ollama: "Educational explanations",
  text_model: "Educational explanations",
  // Not "Document preview" — that's PyMuPDF-rendered and has nothing to do
  // with Ollama; this is what actually powers vision-based extraction.
  vision_model: "AI-assisted extraction",
  embedding_model: "Educational explanations",
  vector_store: "Educational explanations",
  database: "Document storage",
  whisper: "Voice transcription",
  piper: "Voice playback",
  translation_model: "Translation",
  n8n: "Document processing",
  document_processing: "Document preview",
  document_preview: "Document preview",
  processing_jobs: "Processing jobs",
  imaging_documents: "Imaging documents",
  imaging_viewer: "Imaging viewer",
  imaging_reports: "Imaging reports",
  medication_labels: "Medication labels",
  timeline: "Health Timeline",
};

export function friendlyHealthLabel(key: string, fallback?: string) {
  return FRIENDLY_HEALTH_LABELS[key] || fallback || key;
}

export function friendlyComponentStatus(status: string, detail = "") {
  if (status === "ready") return "Available";
  if ((detail || "").toLowerCase().includes("degraded") || status === "degraded") return "Limited";
  return "Unavailable";
}

export function ServiceError({
  title,
  message,
  onRetry,
  onSystem,
}: {
  title: string;
  message: string;
  onRetry?: () => void;
  onSystem?: () => void;
}) {
  return (
    <div className="service-error">
      <Activity size={19} />
      <div>
        <strong>{title}</strong>
        <p>{message}</p>
      </div>
      <div className="service-error-actions">
        {onRetry && (
          <button type="button" onClick={onRetry}>
            <RefreshCw size={15} /> Retry
          </button>
        )}
        {onSystem && (
          <button type="button" onClick={onSystem}>
            <Activity size={15} /> System status
          </button>
        )}
      </div>
    </div>
  );
}

export function MetricCard({
  label,
  value,
  icon: Icon,
  href,
  hint,
}: {
  label: string;
  value: number | string;
  icon: LucideIcon;
  href?: string;
  hint?: string;
}) {
  const content = (
    <>
      <div className="metric-card-icon">
        <Icon size={18} />
      </div>
      <div className="metric-card-body">
        <strong className="metric-card-value">{value}</strong>
        <span className="metric-card-label">{label}</span>
        {hint ? <small className="metric-card-hint">{hint}</small> : null}
      </div>
    </>
  );
  if (href) {
    return (
      <Link href={href} className="metric-card metric-card-link">
        {content}
      </Link>
    );
  }
  return <div className="metric-card">{content}</div>;
}

/**
 * Renders one of loading/error/empty/ready for an `useAsyncData` state,
 * so every list-fetch view gets the same distinguishable states instead of
 * each hand-rolling its own try/catch-to-empty-array pattern.
 */
export function LoadState<T>({
  state,
  isEmpty,
  loading,
  emptyTitle = "Nothing here yet.",
  emptyBody = "",
  errorTitle = "This couldn't be loaded.",
  onRetry,
  children,
}: {
  state: AsyncDataState<T>;
  isEmpty?: (data: T) => boolean;
  loading?: ReactNode;
  emptyTitle?: string;
  emptyBody?: string;
  errorTitle?: string;
  onRetry?: () => void;
  children: (data: T) => ReactNode;
}) {
  if (state.status === "loading") {
    return loading ? (
      <>{loading}</>
    ) : (
      <div className="load-state-loading" role="status" aria-live="polite" aria-label="Loading">
        <span className="load-skeleton" />
        <span className="load-skeleton" />
        <span className="load-skeleton short" />
      </div>
    );
  }
  if (state.status === "error") {
    return <ServiceError title={errorTitle} message={state.error} onRetry={onRetry} />;
  }
  if (isEmpty?.(state.data)) {
    return <EmptyState title={emptyTitle} body={emptyBody} />;
  }
  return <>{children(state.data)}</>;
}

// --------------------------------------------------------------------------
// Core primitives: Button, Input, Table, Tabs, Drawer, StatusChip, Skeleton.
// Reuse the app's existing forest-button/quiet-button/drawer/status-chip
// classes so adopting these doesn't introduce a second visual language —
// it just gives that language a typed, reusable component surface.
// --------------------------------------------------------------------------

export type ButtonVariant = "primary" | "secondary" | "accent" | "ghost" | "destructive";

export function Button({
  variant = "secondary",
  icon: Icon,
  children,
  className = "",
  ...rest
}: {
  variant?: ButtonVariant;
  icon?: LucideIcon;
  children?: ReactNode;
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children">) {
  const base = {
    primary: "forest-button",
    secondary: "quiet-button",
    accent: "accent-button",
    ghost: "ghost-button",
    destructive: "quiet-button destructive-confirm",
  }[variant];
  return (
    <button type="button" className={`${base} ${className}`.trim()} {...rest}>
      {Icon ? <Icon size={15} /> : null}
      {children}
    </button>
  );
}

export function Input({ className = "", ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`ui-input ${className}`.trim()} {...rest} />;
}

export function Table({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className="data-table-wrap">
      <table className={`data-table ${className}`.trim()}>{children}</table>
    </div>
  );
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: string; label: string }[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="ui-tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={active === tab.key}
          className={active === tab.key ? "ui-tab active" : "ui-tab"}
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

/**
 * Shared drawer chrome (backdrop + panel + close button + Escape-to-close +
 * focus return) — consolidates what Privacy/HelpDrawer/SettingsDrawer/Health
 * each hand-rolled separately.
 */
export function Drawer({
  onClose,
  eyebrow,
  title,
  children,
  className = "",
  labelledBy,
}: {
  onClose: () => void;
  eyebrow?: string;
  title?: string;
  children: ReactNode;
  className?: string;
  labelledBy?: string;
}) {
  const titleId = useId();
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previouslyFocused.current?.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="drawer-backdrop" onClick={onClose} role="presentation">
      <aside
        className={`drawer ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy || (title ? titleId : undefined)}
        onClick={(event) => event.stopPropagation()}
      >
        <button className="drawer-close" onClick={onClose} aria-label="Close"><X size={18} /></button>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        {title ? <h2 id={titleId}>{title}</h2> : null}
        {children}
      </aside>
    </div>
  );
}

export type StatusTone = "neutral" | "success" | "warning" | "error";

export function StatusChip({ label, tone = "neutral" }: { label: string; tone?: StatusTone }) {
  return <span className={`status-chip status-chip-${tone}`}>{label}</span>;
}

export function Skeleton({ width, className = "" }: { width?: string | number; className?: string }) {
  return <span className={`load-skeleton ${className}`.trim()} style={width ? { width } : undefined} />;
}
