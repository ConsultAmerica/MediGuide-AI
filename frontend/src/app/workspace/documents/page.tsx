"use client";

import { Suspense, useEffect } from "react";
import { DocumentsView } from "./DocumentsView";
import { useWorkspaceContext } from "../_state/WorkspaceStateProvider";
import { useUrlAction } from "../_state/useUrlAction";

function DocumentsPageContent() {
  const { loadRecentSessions, fileInput, runSyntheticDocumentDemo } = useWorkspaceContext();

  // `loadRecentSessions` is a plain closure recreated every provider
  // render, not a stable useCallback — depending on it here would
  // refetch on every render instead of once per page visit.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void loadRecentSessions(); }, []);

  // Portfolio one-click: the landing CTA (`?action=sample`) loads the
  // three-date synthetic walkthrough; `?action=upload` opens the file picker.
  useUrlAction("/workspace/documents", {
    upload: () => fileInput.current?.click(),
    sample: () => void runSyntheticDocumentDemo(),
  }, 300);

  return <DocumentsView />;
}

export default function DocumentsPage() {
  return (
    <Suspense fallback={null}>
      <DocumentsPageContent />
    </Suspense>
  );
}
