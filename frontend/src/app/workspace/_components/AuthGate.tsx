"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  fetchCurrentUser,
  SESSION_ENDED_EVENT,
  signOut as endSession,
  type AccountUser,
} from "../../../lib/auth";

interface AccountContextValue {
  user: AccountUser;
  signOut: () => Promise<void>;
}

const AccountContext = createContext<AccountContextValue | null>(null);

export function useAccount(): AccountContextValue {
  const value = useContext(AccountContext);
  if (!value) throw new Error("useAccount must be used inside <AuthGate>");
  return value;
}

/** Shows the workspace only to a signed-in user. Everything inside it can
 * assume a valid session; a session that ends mid-use (expiry, sign-out in
 * another tab) sends the user back to sign in, returning here afterwards. */
export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<AccountUser | null>(null);
  const [checking, setChecking] = useState(true);
  const [unreachable, setUnreachable] = useState(false);
  const [attempt, setAttempt] = useState(0);

  const toSignIn = useCallback(
    (reason?: "expired") => {
      const next = encodeURIComponent(`${window.location.pathname}${window.location.search}`);
      router.replace(`/signin?next=${next}${reason ? `&reason=${reason}` : ""}`);
    },
    [router],
  );

  useEffect(() => {
    let cancelled = false;
    fetchCurrentUser()
      .then((current) => {
        if (cancelled) return;
        if (current) setUser(current);
        else toSignIn();
      })
      .catch(() => {
        // A network failure is not a rejected session. Signing in needs the
        // same service, so say what is wrong instead of redirecting.
        if (!cancelled) setUnreachable(true);
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
    // Checked once per workspace mount (and on Retry), not on every
    // client-side navigation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  useEffect(() => {
    const onEnded = () => {
      setUser(null);
      toSignIn("expired");
    };
    window.addEventListener(SESSION_ENDED_EVENT, onEnded);
    return () => window.removeEventListener(SESSION_ENDED_EVENT, onEnded);
  }, [toSignIn]);

  const signOut = useCallback(async () => {
    await endSession();
    setUser(null);
    router.replace("/signin");
  }, [router]);

  if (unreachable) {
    return (
      <main className="auth-gate-loading" role="alert">
        <strong>MediGuide can&apos;t reach its service right now.</strong>
        <p>Check your connection, then try again.</p>
        <button type="button" className="forest-button" onClick={() => { setUnreachable(false); setChecking(true); setAttempt((value) => value + 1); }}>Try again</button>
      </main>
    );
  }

  if (checking || !user) {
    return (
      <main className="auth-gate-loading" aria-busy="true">
        <span className="auth-gate-spinner" aria-hidden />
        <p>Opening your workspace…</p>
      </main>
    );
  }

  return <AccountContext.Provider value={{ user, signOut }}>{children}</AccountContext.Provider>;
}
