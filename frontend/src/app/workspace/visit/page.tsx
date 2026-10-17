"use client";

import { useEffect } from "react";
import { Visit } from "../workspace-views";
import { useWorkspaceContext } from "../_state/WorkspaceStateProvider";

export default function VisitPage() {
  const {
    visitFields, setVisitFields, visitStep, setVisitStep, labSummary, labPoints,
    medFields, generateVisitSummary, loadLabSummary, chatAvailable,
  } = useWorkspaceContext();

  // loadLabSummary is a plain closure recreated every provider render,
  // not a stable useCallback ref — must run once on mount only.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void loadLabSummary(); }, []);

  return (
    <Visit
      fields={visitFields}
      setFields={setVisitFields}
      step={visitStep}
      setStep={setVisitStep}
      labPoints={labSummary.length ? labSummary : labPoints}
      medFields={medFields}
      onGenerate={chatAvailable ? generateVisitSummary : undefined}
    />
  );
}
