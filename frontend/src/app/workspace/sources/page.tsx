"use client";

import { useCallback } from "react";
import { useAsyncData } from "../../../lib/useAsyncData";
import { LoadState } from "../polish-ui";
import { Sources } from "../workspace-views";
import { useWorkspaceContext } from "../_state/WorkspaceStateProvider";
import { API_URL, type LibrarySource } from "../_state/workspace-shared";
import { apiFetch } from "../../../lib/auth";

async function fetchLibrary(): Promise<LibrarySource[]> {
  const response = await apiFetch(`${API_URL}/api/knowledge`);
  if (!response.ok) throw new Error("MediGuide could not load the approved knowledge base.");
  const data = await response.json();
  return data.sources || [];
}

export default function SourcesPage() {
  const { sources, setSelectedSource } = useWorkspaceContext();
  const state = useAsyncData(useCallback(() => fetchLibrary(), []));

  return (
    <LoadState
      state={state}
      errorTitle="Could not load the knowledge base"
      onRetry={state.reload}
    >
      {(library) => <Sources sources={sources} library={library} onSelect={setSelectedSource} />}
    </LoadState>
  );
}
