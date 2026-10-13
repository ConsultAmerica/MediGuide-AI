"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FlaskConical, Lock, ShieldCheck } from "lucide-react";
import { BrandLogo } from "../brand-logo";
import { Tabs } from "../workspace/polish-ui";
import {
  API_BASE_URL,
  fetchCurrentUser,
  register,
  safeNextPath,
  signIn,
  startGuestWorkspace,
  type AccountUser,
} from "../../lib/auth";

type Mode = "signin" | "register";

const API_CONFIGURATION_MESSAGE =
  "This deployment has no MediGuide service URL configured, so signing in isn't possible yet.";

export function SignInForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNextPath(params.get("next"));
  const expired = params.get("reason") === "expired";

  const [mode, setMode] = useState<Mode>(params.get("mode") === "register" ? "register" : "signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"" | "form" | "guest">("");
  // A guest who opens "Create account" keeps their workspace: registering
  // with the guest's session upgrades it in place.
  const [guest, setGuest] = useState<AccountUser | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCurrentUser()
      .then((current) => {
        if (cancelled || !current) return;
        if (current.is_guest) setGuest(current);
        else router.replace(next);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [next, router]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!API_BASE_URL) return setError(API_CONFIGURATION_MESSAGE);
    setError("");
    setBusy("form");
    try {
      if (mode === "signin") await signIn(email, password);
      else await register(email, password, displayName);
      router.replace(next);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Something went wrong. Please try again.");
      setBusy("");
    }
  }

  async function onGuest() {
    if (!API_BASE_URL) return setError(API_CONFIGURATION_MESSAGE);
    setError("");
    setBusy("guest");
    try {
      await startGuestWorkspace();
      router.replace(next);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Something went wrong. Please try again.");
      setBusy("");
    }
  }

  const registering = mode === "register";

  return (
    <div className="signin-card">
      <Link href="/" className="signin-brand" aria-label="MediGuide home">
        <BrandLogo variant="wordmark" />
      </Link>

      <h1>{registering ? (guest ? "Save your workspace" : "Create your account") : "Sign in"}</h1>
      <p className="signin-lead">
        {registering && guest
          ? "Add an email and password to keep everything you've uploaded in this guest workspace."
          : "Your health documents, labs and imaging reports are visible only to your account."}
      </p>

      {expired && !error && (
        <p className="signin-notice" role="status">Your session ended. Sign in again to pick up where you left off.</p>
      )}

      <Tabs
        tabs={[{ key: "signin", label: "Sign in" }, { key: "register", label: "Create account" }]}
        active={mode}
        onChange={(key) => { setMode(key as Mode); setError(""); }}
      />

      <form className="signin-form" onSubmit={onSubmit} noValidate>
        {registering && (
          <label>
            <span>Name <small>(optional)</small></span>
            <input className="ui-input" value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="name" maxLength={128} />
          </label>
        )}
        <label>
          <span>Email</span>
          <input className="ui-input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
        </label>
        <label>
          <span>Password</span>
          <input
            className="ui-input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={registering ? "new-password" : "current-password"}
            minLength={registering ? 10 : undefined}
            aria-describedby={registering ? "password-hint" : undefined}
            required
          />
          {registering && <small id="password-hint">At least 10 characters.</small>}
        </label>

        {error && <p className="signin-error" role="alert">{error}</p>}

        <button type="submit" className="forest-button signin-submit" disabled={Boolean(busy) || !email || !password}>
          <Lock size={15} aria-hidden />
          {busy === "form" ? "Please wait…" : registering ? (guest ? "Save workspace" : "Create account") : "Sign in"}
        </button>
      </form>

      {!guest && (
        <>
          <div className="signin-divider"><span>or</span></div>
          <button type="button" className="quiet-button signin-guest" onClick={() => void onGuest()} disabled={Boolean(busy)}>
            <FlaskConical size={15} aria-hidden />
            {busy === "guest" ? "Opening…" : "Try a private demo workspace"}
          </button>
          <p className="signin-footnote">
            No sign-up needed. Only you can see what you upload there, and you can save it to an account later.
          </p>
        </>
      )}

      <p className="signin-safety"><ShieldCheck size={14} aria-hidden /> Educational tool. Not for emergencies or diagnosis.</p>
    </div>
  );
}
