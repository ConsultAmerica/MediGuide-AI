"use client";

import { useEffect } from "react";

/**
 * One IntersectionObserver for every `[data-reveal]` on the page. Content is
 * visible by default; the `reveal-ready` class that lets CSS hold elements
 * back is only added once this observer is running, so without JavaScript
 * (or with reduced motion, see site.css) nothing is ever hidden.
 */
export function RevealObserver() {
  useEffect(() => {
    const root = document.documentElement;
    const targets = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));
    if (!("IntersectionObserver" in window) || targets.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.12 },
    );
    // Anything already on screen is shown before the class lands, so the
    // first paint never flashes content away.
    const viewportBottom = window.innerHeight;
    for (const target of targets) {
      if (target.getBoundingClientRect().top < viewportBottom) target.classList.add("is-visible");
      else observer.observe(target);
    }
    root.classList.add("reveal-ready");
    return () => {
      observer.disconnect();
      root.classList.remove("reveal-ready");
    };
  }, []);

  return null;
}
