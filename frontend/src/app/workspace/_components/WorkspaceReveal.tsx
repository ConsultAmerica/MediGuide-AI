"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

type Direction = "up" | "left" | "right";

const VIEW_SELECTOR = ".main-panel > .workflow-view, .main-panel > .conversation-view, .main-panel > div > .workflow-view";
/* Sticky, fixed or interactive-in-place pieces that must never move or hide. */
const SKIP_SELECTOR = ".page-hero, .composer, .drawer-backdrop, .load-state-loading, [role='status'], [role='alert']";
const MAX_STAGGER_MS = 420;

/** Card grids enter by column: left column from the left, right column from the right. */
function gridDirection(index: number, columns: number): Direction {
  if (columns < 2) return "up";
  const column = index % columns;
  if (column === 0) return "left";
  if (column === columns - 1) return "right";
  return "up";
}

function columnCount(element: HTMLElement) {
  const template = getComputedStyle(element).gridTemplateColumns;
  return template && template !== "none" ? template.split(" ").length : 1;
}

function release(element: HTMLElement) {
  delete element.dataset.wsReveal;
  delete element.dataset.wsIn;
  element.style.removeProperty("--ws-reveal-delay");
}

function mark(element: HTMLElement, direction: Direction, delayMs: number, observer: IntersectionObserver, pending: Set<HTMLElement>) {
  if (element.dataset.wsSeen !== undefined) return;
  pending.add(element);
  element.dataset.wsSeen = "";
  element.dataset.wsReveal = direction;
  element.style.setProperty("--ws-reveal-delay", `${Math.min(delayMs, MAX_STAGGER_MS)}ms`);
  observer.observe(element);
}

/**
 * Homepage-style scroll reveals for every workspace page. Pages render their
 * content after data loads, so this watches the main panel and tags blocks as
 * they appear. State lives in data attributes React never writes, so a
 * re-render cannot hide revealed content again; `data-ws-seen` stays so an
 * element animates only once. Skipped for reduced motion.
 */
export function WorkspaceReveal() {
  const pathname = usePathname();

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (!("IntersectionObserver" in window)) return;
    const panel = document.querySelector<HTMLElement>(".main-panel");
    if (!panel) return;
    // Tagged but not yet revealed; released on cleanup so nothing stays hidden.
    const pending = new Set<HTMLElement>();
    const timers = new Set<number>();

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const element = entry.target as HTMLElement;
          element.dataset.wsIn = "";
          observer.unobserve(element);
          pending.delete(element);
          // Once settled, hand the element back to its own styles (hover lifts etc.).
          const delayMs = parseInt(element.style.getPropertyValue("--ws-reveal-delay"), 10) || 0;
          const timer = window.setTimeout(() => {
            timers.delete(timer);
            release(element);
          }, delayMs + 1000);
          timers.add(timer);
        }
      },
      { rootMargin: "0px 0px -6% 0px", threshold: 0.08 },
    );

    const scan = () => {
      const view = panel.querySelector<HTMLElement>(VIEW_SELECTOR);
      if (!view) return;
      let blockIndex = 0;
      for (const child of Array.from(view.children) as HTMLElement[]) {
        if (child.matches(SKIP_SELECTOR) || child.closest(SKIP_SELECTOR)) continue;
        const position = getComputedStyle(child).position;
        if (position === "sticky" || position === "fixed") continue;

        // Grids and wrapped rows of cards animate item by item.
        const display = getComputedStyle(child).display;
        const items = (Array.from(child.children) as HTMLElement[]).filter((item) => !item.matches(SKIP_SELECTOR));
        if (display.includes("grid") && items.length > 1) {
          const columns = columnCount(child);
          items.forEach((item, i) => mark(item, gridDirection(i, columns), Math.floor(i / Math.max(columns, 1)) * 90 + (i % columns) * 110, observer, pending));
          continue;
        }
        const isLabel = child.matches(".eyebrow, h3, .sidebar-label");
        mark(child, isLabel ? "left" : "up", (blockIndex++ % 4) * 70, observer, pending);
      }
    };

    let frame = 0;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(scan);
    };
    scan();
    const mutations = new MutationObserver(schedule);
    mutations.observe(panel, { childList: true, subtree: true });

    return () => {
      cancelAnimationFrame(frame);
      mutations.disconnect();
      observer.disconnect();
      timers.forEach((timer) => window.clearTimeout(timer));
      // Anything still waiting is shown as-is and may be tagged again by the next run.
      panel.querySelectorAll<HTMLElement>("[data-ws-seen]").forEach((element) => {
        release(element);
        if (pending.has(element)) delete element.dataset.wsSeen;
      });
    };
  }, [pathname]);

  return null;
}
