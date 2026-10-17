"use client";

import { Suspense, useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { LabTimeline } from "../workspace-views";
import { useWorkspaceContext } from "../_state/WorkspaceStateProvider";

// The URL is the source of truth for what Labs shows:
//   /workspace/labs?test=<code>&point=<observation_id>
// so a refresh, a shared link, or Back/Forward lands on the same test and
// the same open result. Choosing a test or opening a result pushes a
// history entry (Back steps back through them); closing the result
// replaces it.
function LabsPageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const testParam = searchParams.get("test");
  const pointParam = searchParams.get("point");

  const {
    labTests, selectedLabCode, setSelectedLabCode, labPoints, selectedLabPoint,
    setSelectedLabPoint, inspectDocument, exportLabPoints, addLabsToVisit,
    askAboutLabs, chatAvailable, setConfirmDeleteObservationId, handleViewChange,
    loadLabs, loadLabSummary,
  } = useWorkspaceContext();

  function labsUrl(test: string, point?: string | null) {
    const params = new URLSearchParams({ test });
    if (point) params.set("point", point);
    return `${pathname}?${params.toString()}`;
  }

  // Arriving without ?test= (sidebar, or a cross-link that already set the
  // selection in state) records the current selection in the URL.
  useEffect(() => {
    if (!testParam) router.replace(labsUrl(selectedLabCode));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testParam]);

  // URL -> selected test. loadLabs/loadLabSummary are plain closures
  // recreated every provider render, not stable useCallback refs.
  useEffect(() => {
    if (!testParam) return;
    if (testParam !== selectedLabCode) setSelectedLabCode(testParam);
    void loadLabs(testParam);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testParam]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void loadLabSummary(); }, []);

  // URL -> open result, once that test's points have loaded. A point id
  // that isn't in the list (deleted, or another test's) just stays closed.
  useEffect(() => {
    const match = pointParam ? labPoints.find((point) => point.observation_id === pointParam) ?? null : null;
    if ((match?.observation_id ?? null) !== (selectedLabPoint?.observation_id ?? null)) setSelectedLabPoint(match);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pointParam, labPoints]);

  const activeTest = testParam || selectedLabCode;

  return (
    <LabTimeline
      tests={labTests}
      selectedCode={activeTest}
      onSelectCode={(code) => router.push(labsUrl(code))}
      points={labPoints}
      selectedPoint={selectedLabPoint}
      onSelectPoint={(point) => {
        if (point) router.push(labsUrl(activeTest, point.observation_id));
        else router.replace(labsUrl(activeTest));
      }}
      onInspectDocument={(documentId, pageNumber, fieldId) => void inspectDocument(documentId, pageNumber, fieldId)}
      onExport={exportLabPoints}
      onAddToVisit={addLabsToVisit}
      onAskAbout={chatAvailable ? askAboutLabs : undefined}
      onRequestDeleteObservation={(observationId) => setConfirmDeleteObservationId(observationId)}
      onOpenDocuments={() => handleViewChange("documents")}
    />
  );
}

export default function LabsPage() {
  return (
    <Suspense fallback={null}>
      <LabsPageContent />
    </Suspense>
  );
}
