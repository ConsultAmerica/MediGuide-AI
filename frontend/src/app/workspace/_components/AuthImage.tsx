"use client";

import { useEffect, useState, type CSSProperties } from "react";
import { apiFetch } from "../../../lib/auth";

/**
 * An <img> for owner-only API images (page and label previews). A plain
 * <img src> can't send the session header, so the image is fetched with
 * apiFetch and shown from a local object URL.
 */
export function AuthImage({
  src,
  alt,
  className,
  style,
  onError,
}: {
  src: string;
  alt: string;
  className?: string;
  style?: CSSProperties;
  onError?: () => void;
}) {
  // Keyed by src so a stale image never shows while the next page loads.
  const [loaded, setLoaded] = useState<{ src: string; url: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let created = "";
    apiFetch(src)
      .then(async (response) => {
        if (!response.ok) throw new Error(`Preview request failed (${response.status})`);
        const blob = await response.blob();
        if (cancelled) return;
        created = URL.createObjectURL(blob);
        setLoaded({ src, url: created });
      })
      .catch(() => {
        if (!cancelled) onError?.();
      });
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
    // onError is a notification callback; re-fetching when its identity
    // changes on every parent render would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  const objectUrl = loaded?.src === src ? loaded.url : "";
  if (!objectUrl) return <span className="auth-image-loading" role="img" aria-label={`${alt} (loading)`} />;
  // eslint-disable-next-line @next/next/no-img-element -- a local blob URL; next/image can't optimize it
  return <img src={objectUrl} alt={alt} className={className} style={style} />;
}
