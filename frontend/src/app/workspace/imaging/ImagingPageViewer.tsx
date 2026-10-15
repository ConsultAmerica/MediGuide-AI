"use client";

import { useState, type ReactNode } from "react";
import { AuthImage } from "../_components/AuthImage";
import type { SourceRegion } from "./imaging-types";

/**
 * One page of the report, with the selected section's wording outlined when
 * its position on the page is known. Without a recorded position nothing is
 * drawn; the note says so instead. Page navigation stops at the report's
 * last page.
 */
export function ImagingPageViewer({
  src,
  page,
  pageCount,
  onPage,
  regions,
  note,
  className = "",
  extraControls,
}: {
  src: string;
  page: number;
  pageCount?: number | null;
  onPage?: (page: number) => void;
  /** Regions to outline on this page (already filtered to this page). */
  regions: SourceRegion[];
  note?: string;
  className?: string;
  extraControls?: ReactNode;
}) {
  // Keyed by src so a failed page doesn't keep the next page hidden.
  const [failedSrc, setFailedSrc] = useState("");
  const failed = failedSrc === src;
  const size = regions[0];

  return (
    <div className={`document-preview imaging-viewer ${className}`.trim()}>
      {!src || failed ? (
        <span>No preview is available for this page.</span>
      ) : size ? (
        <div className="imaging-page-frame" style={{ aspectRatio: `${size.width} / ${size.height}` }}>
          <AuthImage src={src} alt={`Page ${page}`} onError={() => setFailedSrc(src)} />
          {regions.map((region, index) => {
            const [x0, y0, x1, y1] = region.bbox;
            const padX = region.width * 0.008;
            const padY = region.height * 0.004;
            return (
              <span
                key={index}
                className="imaging-source-region"
                aria-hidden="true"
                style={{
                  left: `${(Math.max(0, x0 - padX) / region.width) * 100}%`,
                  top: `${(Math.max(0, y0 - padY) / region.height) * 100}%`,
                  width: `${((Math.min(region.width, x1 + padX) - Math.max(0, x0 - padX)) / region.width) * 100}%`,
                  height: `${((Math.min(region.height, y1 + padY) - Math.max(0, y0 - padY)) / region.height) * 100}%`,
                }}
              />
            );
          })}
        </div>
      ) : (
        <AuthImage src={src} alt={`Page ${page}`} onError={() => setFailedSrc(src)} />
      )}
      {note ? <p className="imaging-viewer-note" aria-live="polite">{note}</p> : null}
      {onPage && (
        <div className="imaging-page-nav">
          <button type="button" className="quiet-button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
            Previous page
          </button>
          <span>Page {page}{pageCount ? ` of ${pageCount}` : ""}</span>
          <button type="button" className="quiet-button" disabled={Boolean(pageCount) && page >= (pageCount || 1)} onClick={() => onPage(page + 1)}>
            Next page
          </button>
          {extraControls}
        </div>
      )}
    </div>
  );
}
