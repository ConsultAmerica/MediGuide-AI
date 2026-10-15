"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { HelpCircle, Menu, Search, Settings, UserRound } from "lucide-react";
import { BrandLogo } from "../../brand-logo";
import { ConfirmDialog, ToastStack } from "../polish-ui";
import { useWorkspaceContext } from "../_state/WorkspaceStateProvider";
import { Sidebar } from "./Sidebar";
import { CommandPalette } from "./CommandPalette";
import { WorkspaceReveal } from "./WorkspaceReveal";
import { serviceStateFrom } from "./serviceState";
import {
  Composer,
  Evidence,
  Health,
  HelpDrawer,
  Privacy,
  SettingsDrawer,
  TranscriptReview,
} from "../workspace-views";

// The Composer/TranscriptReview footer is shared by Ask and Sources — Sources
// lets you type a follow-up question while browsing citations, mirroring the
// pre-routing behavior where both views fell through the same "not a
// dedicated workflow" branch.
const COMPOSER_ROUTES = new Set(["/workspace/ask", "/workspace/sources"]);

// The citations panel only appears where citations can exist; elsewhere the
// page gets the full width instead of an empty side column.
const EVIDENCE_ROUTE_PREFIXES = ["/workspace/ask", "/workspace/sources", "/workspace/documents"];

export function WorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const {
    router,
    mobileNavOpen, setMobileNavOpen,
    language, translateAnswer,
    setHealthOpen, setHelpOpen, setSettingsOpen, setPrivacyOpen,
    health, healthOpen, helpOpen, settingsOpen, privacyOpen,
    checkHealth,
    handleViewChange,
    clearSession,
    toasts, setToasts,
    confirmDeleteObservationId, setConfirmDeleteObservationId, deleteLabObservation,
    confirmResetDocument, setConfirmResetDocument, deleteDocument,
    pushToast,
    fileInput, medFileInput, onFileChange, onMedFileChange,
    question, setQuestion, sendQuestion, handleComposerKey, toggleVoice, recording, loadingStage,
    answerDetail, setAnswerDetail, readingLevel, setReadingLevel,
    pendingTranscript, setPendingTranscript, transcriptReviewed, setTranscriptReviewed, confirmTranscript,
    evidenceSources, evidenceContext, selectedSource, setSelectedSource,
    setLanguage,
  } = useWorkspaceContext();

  // The header dot reports what /api/health actually said, never a default "healthy".
  const serviceState = serviceStateFrom(health);

  const showComposer = COMPOSER_ROUTES.has(pathname);
  const showEvidence = EVIDENCE_ROUTE_PREFIXES.some((prefix) => pathname.startsWith(prefix));

  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      // Don't hijack the shortcut while the user is actively composing text
      // in the main chat input — Cmd/Ctrl+K there would be surprising.
      const target = event.target as HTMLElement | null;
      const isComposerTextarea = target?.tagName === "TEXTAREA" && target.closest(".composer");
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && !isComposerTextarea) {
        event.preventDefault();
        setCommandPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <main className="product-shell workspace-enter">
      <header className="app-header">
        <button className="app-brand" onClick={() => router.push("/")} aria-label="MediGuide home page">
          <BrandLogo variant="wordmark" className="brand-logo-header" />
        </button>
        <span className="header-context">Health Document Intelligence</span>
        <div className="header-actions">
          <select className="language-select" value={language} onChange={(event) => void translateAnswer(event.target.value)} aria-label="Response language">
            <option>English</option><option>Spanish</option><option>French</option>
          </select>
          <button className={`local-pill service-${serviceState.tone}`} onClick={() => setHealthOpen(true)} aria-label={`Service status: ${serviceState.label}`} title={serviceState.label}>
            <span aria-hidden="true" /> Service status
          </button>
          <button className="icon-button header-search-trigger" title="Search (Ctrl/⌘K)" aria-label="Search your health information" onClick={() => setCommandPaletteOpen(true)}><Search size={18} /></button>
          <button className="icon-button" title="Help" aria-label="Help" onClick={() => setHelpOpen(true)}><HelpCircle size={18} /></button>
          <button className="icon-button" title="Settings" aria-label="Settings" onClick={() => setSettingsOpen(true)}><Settings size={18} /></button>
          <button className="profile-button" title="Privacy" aria-label="Privacy" onClick={() => setPrivacyOpen(true)}><UserRound size={17} /></button>
        </div>
        {/* Phones have no Ctrl+K: search stays one tap away beside the menu. */}
        <button className="icon-button mobile-search-trigger" title="Search" aria-label="Search your health information" onClick={() => setCommandPaletteOpen(true)}><Search size={18} /></button>
        <button className="mobile-menu icon-button" title="Open navigation" aria-label="Open navigation" aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen(true)}><Menu size={20} /></button>
      </header>
      {mobileNavOpen && <button className="mobile-nav-backdrop" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} />}
      <div className={`workspace-grid${mobileNavOpen ? " mobile-nav-visible" : ""}${showEvidence ? "" : " no-evidence"}`}>
        <Sidebar onClose={() => setMobileNavOpen(false)} />
        <section className="main-panel">
          <WorkspaceReveal />
          {children}
          {showComposer && (
            <>
              {pendingTranscript && (
                <TranscriptReview
                  text={pendingTranscript}
                  setText={setPendingTranscript}
                  reviewed={transcriptReviewed}
                  setReviewed={setTranscriptReviewed}
                  onConfirm={confirmTranscript}
                  onDiscard={() => { setPendingTranscript(""); setTranscriptReviewed(false); }}
                />
              )}
              <Composer
                question={question}
                setQuestion={setQuestion}
                onSubmit={sendQuestion}
                onKeyDown={handleComposerKey}
                onUpload={() => fileInput.current?.click()}
                onVoice={toggleVoice}
                recording={recording}
                loading={Boolean(loadingStage)}
                answerDetail={answerDetail}
                setAnswerDetail={setAnswerDetail}
                readingLevel={readingLevel}
                setReadingLevel={setReadingLevel}
              />
            </>
          )}
          <input ref={fileInput} type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,image/*" hidden onChange={onFileChange} />
          <input ref={medFileInput} type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,image/*" hidden onChange={onMedFileChange} />
        </section>
        {showEvidence && (
          <Evidence
            sources={evidenceSources}
            selected={selectedSource}
            onSelect={setSelectedSource}
            context={evidenceContext}
            onOpenSources={() => handleViewChange("sources")}
          />
        )}
      </div>
      <ToastStack toasts={toasts} onDismiss={(id) => setToasts((current) => current.filter((item) => item.id !== id))} />
      <ConfirmDialog
        open={Boolean(confirmDeleteObservationId)}
        title="Delete this result?"
        body="This removes the timeline observation only. The source document stays available until you clear it separately."
        confirmLabel="Delete result"
        destructive
        onCancel={() => setConfirmDeleteObservationId(null)}
        onConfirm={() => { if (confirmDeleteObservationId) void deleteLabObservation(confirmDeleteObservationId); }}
      />
      <ConfirmDialog
        open={confirmResetDocument}
        title="Clear this document?"
        body="This permanently deletes the uploaded file, its page previews, and any lab results confirmed from it. This can't be undone."
        confirmLabel="Delete document"
        destructive
        onCancel={() => setConfirmResetDocument(false)}
        onConfirm={() => { setConfirmResetDocument(false); void deleteDocument().then((deleted) => { if (deleted) { router.push("/workspace/documents"); pushToast("Document deleted", "info"); } }); }}
      />
      {privacyOpen && <Privacy onClose={() => setPrivacyOpen(false)} onClear={clearSession} />}
      {helpOpen && <HelpDrawer onClose={() => setHelpOpen(false)} onOpenView={(next) => { setHelpOpen(false); handleViewChange(next); }} />}
      {settingsOpen && (
        <SettingsDrawer
          answerDetail={answerDetail}
          setAnswerDetail={setAnswerDetail}
          readingLevel={readingLevel}
          setReadingLevel={setReadingLevel}
          language={language}
          setLanguage={setLanguage}
          onClose={() => setSettingsOpen(false)}
        />
      )}
      {healthOpen && <Health health={health} onClose={() => setHealthOpen(false)} onRetry={checkHealth} />}
      {commandPaletteOpen && <CommandPalette onClose={() => setCommandPaletteOpen(false)} />}
    </main>
  );
}
