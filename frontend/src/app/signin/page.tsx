import type { Metadata } from "next";
import { Suspense } from "react";
import { SignInForm } from "./SignInForm";
import "../workspace.css";

export const metadata: Metadata = {
  title: "Sign in · MediGuide",
  description: "Sign in to your MediGuide health records, or open a private demo workspace.",
};

export default function SignInPage() {
  return (
    <main className="signin-page">
      <Suspense fallback={<div className="signin-card" aria-busy="true" />}>
        <SignInForm />
      </Suspense>
    </main>
  );
}
