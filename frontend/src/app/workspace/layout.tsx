import type { ReactNode } from "react";
import { WorkspaceStateProvider } from "./_state/WorkspaceStateProvider";
import { WorkspaceShell } from "./_components/WorkspaceShell";
import { AuthGate } from "./_components/AuthGate";
import "../workspace.css";
import "./workspace-theme.css";

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <WorkspaceStateProvider>
        <WorkspaceShell>{children}</WorkspaceShell>
      </WorkspaceStateProvider>
    </AuthGate>
  );
}
