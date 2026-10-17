"use client";

import { Conversation } from "../workspace-views";
import { useWorkspaceContext } from "../_state/WorkspaceStateProvider";

export default function AskPage() {
  const {
    answer, answerStatus, streaming, sources, question, setQuestion, messages,
    loadingStage, error, selectedSource, setSelectedSource, retry,
    handleViewChange, openDocumentPage, fileInput, copyAnswer, readAnswer,
    sendQuestion, aiAvailable, chatAvailable,
  } = useWorkspaceContext();

  return (
    <Conversation
      aiAvailable={aiAvailable}
      chatAvailable={chatAvailable}
      answer={answer}
      status={answerStatus}
      streaming={streaming}
      sources={sources}
      question={question}
      messages={messages}
      loading={loadingStage}
      error={error}
      selectedSource={selectedSource}
      setSelectedSource={setSelectedSource}
      onRetry={retry}
      onPreset={(prompt) => setQuestion(prompt)}
      onOpenView={handleViewChange}
      onOpenDocumentPage={openDocumentPage}
      onUpload={() => fileInput.current?.click()}
      onAction={(action) => {
        if (action === "copy") copyAnswer();
        if (action === "listen") readAnswer();
        if (action === "simple") void sendQuestion(undefined, `Explain this answer simply:\n\n${answer}`);
        if (action === "questions") setQuestion("What questions should I ask my clinician about this?");
      }}
    />
  );
}
