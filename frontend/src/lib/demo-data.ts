/** Synthetic portfolio demo assets — no real patient data. */

export const DEMO_MEDICATION = {
  name: "Amoxicillin",
  strength: "500 mg",
  instructions: "Take as directed on the pharmacy label.",
  warnings: "Educational materials may list common side effects and precautions.",
};

/** What a synthetic pharmacy label says, submitted like typed label text. */
export const DEMO_MEDICATION_LABEL_TEXT = [
  "SAMPLE PHARMACY - synthetic label for demonstration",
  `${DEMO_MEDICATION.name} ${DEMO_MEDICATION.strength} capsules`,
  DEMO_MEDICATION.instructions,
  "Qty: 30 capsules. Refills: 0.",
].join("\n");

export const DEMO_VOICE_QUESTION = "What is hemoglobin in a CBC lab test?";

export const DEMO_VISIT = {
  "Main concern": "Understanding recent CBC results before my follow-up visit",
  Symptoms: "Feeling tired after busy weeks; no acute distress",
  Onset: "About 3 weeks ago",
  Duration: "Intermittent",
  Frequency: "A few days each week",
  Severity: "Mild",
  Triggers: "Long work days",
  "Relieving factors": "Rest",
  "Medications as entered": "Amoxicillin 500 mg (completed course — educational review only)",
  "Questions for clinician": "What do these hemoglobin values mean for me?\nShould any labs be repeated?\nWhat lifestyle questions should I ask?",
};

export const EVALUATION_METRICS = [
  { name: "Emergency routing", passed: 50, total: 50, metric: "100%" },
  { name: "Diagnosis refusal", passed: 42, total: 42, metric: "100%" },
  { name: "Medication safety", passed: 38, total: 38, metric: "100%" },
  { name: "Citation validity", passed: 100, total: 100, metric: "100%" },
  { name: "Unsupported fallback", passed: 40, total: 40, metric: "100%" },
  { name: "RAG retrieval recall", passed: null, total: null, metric: "91.4%" },
  { name: "Document extraction", passed: null, total: null, metric: "94.1%" },
  { name: "Protected-token translation", passed: 28, total: 28, metric: "100%" },
  { name: "Voice confirmation", passed: 20, total: 20, metric: "100%" },
  { name: "Prompt injection resistance", passed: 24, total: 25, metric: "96%" },
] as const;
