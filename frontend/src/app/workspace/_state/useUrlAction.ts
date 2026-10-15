"use client";

import { useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";

/**
 * Runs the handler for `?action=<name>` once per arrival, then drops the
 * query from the URL.
 *
 * Why not a plain effect with a cleanup: `router.replace()` changes the
 * search params, which re-runs the effect, and the cleanup cancelled the
 * pending timer before it fired. Deep links such as the homepage "Try it
 * with synthetic data" (`?action=sample`) then silently did nothing. The
 * ref also absorbs React's development double-run so a handler never runs
 * twice, and resets once the param is gone so the same link works again.
 */
export function useUrlAction(basePath: string, handlers: Record<string, () => void>, delayMs = 250) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const handled = useRef<string | null>(null);
  const latest = useRef(handlers);
  useEffect(() => {
    latest.current = handlers;
  });

  useEffect(() => {
    const action = searchParams.get("action");
    if (!action) {
      handled.current = null;
      return;
    }
    if (handled.current === action || !latest.current[action]) return;
    handled.current = action;
    router.replace(basePath);
    window.setTimeout(() => latest.current[action]?.(), delayMs);
  }, [searchParams, router, basePath, delayMs]);
}
