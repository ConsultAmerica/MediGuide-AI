"use client";

import { useEffect, useRef, useState } from "react";
import type { LabPoint } from "../_state/workspace-shared";

const PAD = { top: 30, right: 24, bottom: 40, left: 48 };
// Points sit inset from the plot edges so their labels clear the axis.
const INSET = 36;
const DAY_MS = 86_400_000;

function niceRange(values: number[], low?: number | null, high?: number | null): [number, number] {
  const all = [...values, ...(low != null ? [low] : []), ...(high != null ? [high] : [])];
  let min = Math.min(...all);
  let max = Math.max(...all);
  if (min === max) {
    min -= Math.abs(min) * 0.1 || 1;
    max += Math.abs(max) * 0.1 || 1;
  }
  const pad = (max - min) * 0.18;
  return [min - pad, max + pad];
}

function ticks(min: number, max: number, count = 4): number[] {
  const step = (max - min) / count;
  const magnitude = 10 ** Math.floor(Math.log10(step));
  const nice = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((m) => m >= step) ?? step;
  const start = Math.ceil(min / nice) * nice;
  const out: number[] = [];
  for (let v = start; v <= max + 1e-9; v += nice) out.push(Number(v.toFixed(6)));
  return out;
}

/** Ticks share one precision so the axis reads 6.0 / 6.5, not 6 / 6.5. */
function tickFormatter(values: number[]) {
  const decimals = Math.min(2, Math.max(0, ...values.map((v) => (String(v).split(".")[1] || "").length)));
  return (v: number) => v.toFixed(decimals);
}

function dayNumber(value?: string | null): number | null {
  if (!value) return null;
  const time = new Date(`${value}T00:00:00Z`).getTime();
  return Number.isNaN(time) ? null : Math.round(time / DAY_MS);
}

/** Whether the chart may draw a point: the server decides (date, plain
 * number, series unit, not a repeat); older responses fall back to "has a
 * number and a date". */
export function isPlottable(point: LabPoint): boolean {
  if (typeof point.plotted === "boolean") return point.plotted;
  return typeof point.value === "number" && Boolean(point.date || point.collection_date || point.report_date);
}

/**
 * Confirmed results for one test over time, spaced by their real dates.
 * Only comparable results are drawn (same unit, plain numbers, dated, no
 * repeats); the table below the chart lists everything. The shaded band is
 * the range printed on the reports, shown only when every point shares it.
 * Points are buttons, so the chart is fully keyboard operable and each one
 * opens that value's provenance.
 */
export function LabTrendChart({
  points,
  selectedId,
  onSelect,
  formatDate,
  testName,
}: {
  points: LabPoint[];
  selectedId?: string | null;
  onSelect: (point: LabPoint) => void;
  formatDate: (value?: string | null) => string;
  testName: string;
}) {
  // Drawn at the container's real width (1 unit = 1px), so text stays the
  // same size on a phone and a wide desktop instead of scaling with it.
  const frame = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(720);
  useEffect(() => {
    const el = frame.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    // Small changes are ignored so a scrollbar appearing can never start a
    // resize loop (the chart redrawing, the page height changing, the width
    // changing again).
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.max(280, Math.round(entry.contentRect.width));
      setW((current) => (Math.abs(current - next) > 24 ? next : current));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  // Fixed height: the chart only ever reflows horizontally.
  const H = W < 520 ? 230 : 280;

  const plotted = points.filter((p) => isPlottable(p) && typeof p.value === "number");
  if (!plotted.length) return null;
  const dateOf = (p: LabPoint) => p.date || p.collection_date || p.report_date || null;

  // Draw a reference band only when every point shares the same printed range.
  const low = plotted[0].reference_low ?? null;
  const high = plotted[0].reference_high ?? null;
  const sharedRange = plotted.every((p) => (p.reference_low ?? null) === low && (p.reference_high ?? null) === high);
  const bandLow = sharedRange ? low : null;
  const bandHigh = sharedRange ? high : null;

  const [min, max] = niceRange(plotted.map((p) => p.value as number), bandLow, bandHigh);
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  // Time-proportional: a year between results looks like a year, not like
  // the gap between two results a week apart.
  const days = plotted.map((p) => dayNumber(dateOf(p)));
  const firstDay = Math.min(...days.map((d) => d ?? 0));
  const lastDay = Math.max(...days.map((d) => d ?? 0));
  const span = lastDay - firstDay;
  const x = (i: number) => {
    if (plotted.length === 1 || span <= 0 || days[i] == null) {
      return PAD.left + (plotted.length === 1 || span <= 0 ? innerW / 2 : INSET + (i * (innerW - INSET * 2)) / (plotted.length - 1));
    }
    return PAD.left + INSET + (((days[i] as number) - firstDay) / span) * (innerW - INSET * 2);
  };
  const y = (v: number) => PAD.top + ((max - v) / (max - min)) * innerH;
  const xs = plotted.map((_, i) => x(i));
  const line = plotted.map((p, i) => `${i ? "L" : "M"}${xs[i].toFixed(1)} ${y(p.value as number).toFixed(1)}`).join(" ");
  const unit = plotted[plotted.length - 1].unit;
  const yTicks = ticks(min, max);
  const formatTick = tickFormatter(yTicks);

  // Label as many dates/values as fit without overlapping; the last result
  // is always labelled. Unlabelled points still name themselves to screen
  // readers and in their tooltip, and every value is in the table.
  const dateLabelGap = W < 520 ? 74 : 92;
  const valueLabelGap = 40;
  const showDate: boolean[] = plotted.map(() => false);
  const showValue: boolean[] = plotted.map(() => false);
  let lastDateX = Infinity;
  let lastValueX = Infinity;
  for (let i = plotted.length - 1; i >= 0; i -= 1) {
    if (lastDateX - xs[i] >= dateLabelGap) { showDate[i] = true; lastDateX = xs[i]; }
    if (lastValueX - xs[i] >= valueLabelGap || plotted[i].observation_id === selectedId) { showValue[i] = true; lastValueX = xs[i]; }
  }
  const neighbourGaps = xs.map((value, i) => Math.min(i > 0 ? value - xs[i - 1] : Infinity, i < xs.length - 1 ? xs[i + 1] - value : Infinity));
  const hitWidth = (i: number) => Math.max(28, Math.min(96, (Number.isFinite(neighbourGaps[i]) ? neighbourGaps[i] : innerW) - 6));

  const bandTop = bandHigh != null ? y(Math.min(bandHigh, max)) : PAD.top;
  const bandBottom = bandLow != null ? y(Math.max(bandLow, min)) : PAD.top + innerH;
  const showBand = sharedRange && (bandLow != null || bandHigh != null);
  const rangeLabel = bandLow != null && bandHigh != null ? `${bandLow}–${bandHigh}` : bandHigh != null ? `under ${bandHigh}` : `over ${bandLow}`;

  return (
    <figure className="lab-trend-chart" ref={frame}>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="group" aria-label={`${testName} confirmed results over time, in ${unit || "the printed unit"}`}>
        {showBand && (
          <g aria-hidden="true">
            <rect className="ltc-band" x={PAD.left} y={bandTop} width={innerW} height={Math.max(0, bandBottom - bandTop)} rx="6" />
            <text className="ltc-band-label" x={PAD.left + 10} y={bandBottom - 8}>Printed range {rangeLabel}</text>
          </g>
        )}
        <g aria-hidden="true">
          {yTicks.map((t) => (
            <g key={t}>
              <line className="ltc-grid" x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} />
              <text className="ltc-axis" x={PAD.left - 10} y={y(t) + 4} textAnchor="end">{formatTick(t)}</text>
            </g>
          ))}
          {unit && <text className="ltc-axis ltc-unit" x={PAD.left - 10} y={PAD.top - 14} textAnchor="end">{unit}</text>}
          {plotted.length > 1 && <path className="ltc-line" d={line} />}
        </g>
        {plotted.map((p, i) => {
          const selected = p.observation_id === selectedId;
          const dateText = formatDate(dateOf(p));
          const label = `${p.value_text} ${p.unit}, ${dateText}. Open provenance`;
          return (
            <g
              key={p.observation_id}
              className={selected ? "ltc-point is-selected" : "ltc-point"}
              role="button"
              tabIndex={0}
              aria-label={label}
              aria-pressed={selected}
              onClick={() => onSelect(p)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(p);
                }
              }}
            >
              <title>{`${p.value_text} ${p.unit} · ${p.date_source === "collection" ? "collected" : "dated"} ${dateText} · ${p.document_name}, page ${p.source_page || p.page_number}`}</title>
              {/* The whole column is the target, not just the 13px dot. */}
              <rect className="ltc-hit" x={xs[i] - hitWidth(i) / 2} y={PAD.top - 20} width={hitWidth(i)} height={H - PAD.top + 20} rx="12" />
              <circle className="ltc-dot" cx={xs[i]} cy={y(p.value as number)} r={selected ? 8 : 6.5} />
              {showValue[i] && <text className="ltc-value" x={xs[i]} y={y(p.value as number) - 16} textAnchor="middle">{p.value_text}</text>}
              {showDate[i] && <text className="ltc-axis" x={xs[i]} y={H - 14} textAnchor="middle">{dateText}</text>}
            </g>
          );
        })}
      </svg>
      <figcaption className="ltc-legend">
        <span><i className="ltc-legend-line" /> {plotted.length > 1 ? `Your confirmed results (${unit})` : `One confirmed result (${unit}), so no trend is shown`}</span>
        {showBand ? (
          <span><i className="ltc-legend-band" /> Range printed on the report</span>
        ) : (
          <span>{sharedRange ? "No numeric range printed on these reports" : "Reports list different ranges, so none is shaded"}</span>
        )}
        <span>Spaced by date</span>
      </figcaption>
    </figure>
  );
}
