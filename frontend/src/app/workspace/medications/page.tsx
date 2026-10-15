"use client";

import { Suspense } from "react";
import { Medication } from "../workspace-views";
import { useUrlAction } from "../_state/useUrlAction";
import { useWorkspaceContext } from "../_state/WorkspaceStateProvider";
import { API_URL } from "../_state/workspace-shared";

function MedicationsPageContent() {
  const {
    medState, medConfirmed, applyMedState,
    medInfo, medQuestion, setMedQuestion, medTypedText, setMedTypedText,
    selectedSource, setSelectedSource, medDragging, setMedDragging, medFileInput,
    onMedDrop, getMedicationInfo,
    submitTypedMedication, loadDemoMedication, prepareVisitFromMedication,
    resetMedication, loadingStage, error,
  } = useWorkspaceContext();

  useUrlAction("/workspace/medications", { upload: () => medFileInput.current?.click() }, 300);

  return (
    <Medication
      apiUrl={API_URL}
      medState={medState}
      medConfirmed={medConfirmed}
      onStateChange={applyMedState}
      medInfo={medInfo}
      medQuestion={medQuestion}
      setMedQuestion={setMedQuestion}
      medTypedText={medTypedText}
      setMedTypedText={setMedTypedText}
      selectedSource={selectedSource}
      setSelectedSource={setSelectedSource}
      dragging={medDragging}
      onUpload={() => medFileInput.current?.click()}
      onDrop={onMedDrop}
      onDragEnter={() => setMedDragging(true)}
      onDragLeave={() => setMedDragging(false)}
      onGetInfo={() => void getMedicationInfo()}
      onSubmitTyped={() => void submitTypedMedication(medTypedText)}
      onSample={loadDemoMedication}
      onPrepareVisit={prepareVisitFromMedication}
      onReset={resetMedication}
      loading={loadingStage}
      error={error}
    />
  );
}

export default function MedicationsPage() {
  return (
    <Suspense fallback={null}>
      <MedicationsPageContent />
    </Suspense>
  );
}
