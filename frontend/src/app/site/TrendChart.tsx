import { A1C_POINTS, A1C_RANGE_HIGH } from "./data";

const MIN = 5.2;
const MAX = 7.0;

// Each size has its own coordinate space, so text stays a sensible size
// instead of scaling up with the card.
const SIZES = {
  compact: { W: 320, H: 150, pad: { top: 18, right: 16, bottom: 30, left: 16 }, inset: 26, axis: false },
  wide: { W: 640, H: 240, pad: { top: 24, right: 20, bottom: 34, left: 40 }, inset: 44, axis: true },
} as const;

/**
 * Hemoglobin A1C across three synthetic reports, with the report's printed
 * range (<5.7%) shaded. The line draws itself when an ancestor gains
 * `.is-visible` (see RevealObserver), or immediately with `animateOnLoad`.
 */
export function TrendChart({ animateOnLoad = false, size = "compact" }: { animateOnLoad?: boolean; size?: keyof typeof SIZES }) {
  const { W, H, pad, inset, axis } = SIZES[size];
  const x = (i: number) => pad.left + inset + (i * (W - pad.left - pad.right - inset * 2)) / (A1C_POINTS.length - 1);
  const y = (v: number) => pad.top + ((MAX - v) / (MAX - MIN)) * (H - pad.top - pad.bottom);
  const line = A1C_POINTS.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ");
  const bandTop = y(A1C_RANGE_HIGH);
  const plotBottom = H - pad.bottom;

  return (
    <svg
      className={`trend-chart trend-chart-${size}${animateOnLoad ? " trend-chart-load" : ""}`}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Hemoglobin A1C rose from 6.2% in January to 6.5% in April and 6.7% in August 2026, above the report's printed range of under 5.7%."
    >
      <rect className="trend-band" x={pad.left} y={bandTop} width={W - pad.left - pad.right} height={plotBottom - bandTop} rx="4" />
      {[6.0, 6.5, 7.0].map((tick) => (
        <g key={tick}>
          <line className="trend-grid" x1={pad.left} x2={W - pad.right} y1={y(tick)} y2={y(tick)} />
          {axis && <text className="trend-axis" x={pad.left - 10} y={y(tick) + 4} textAnchor="end">{tick.toFixed(1)}</text>}
        </g>
      ))}
      <text className="trend-band-label" x={pad.left + 10} y={plotBottom - 8}>Printed range &lt;5.7</text>
      <path className="trend-line" d={line} pathLength={1} />
      {A1C_POINTS.map((p, i) => (
        <g key={p.label} className="trend-point" style={{ ["--i" as string]: i }}>
          <circle cx={x(i)} cy={y(p.value)} r={size === "wide" ? 6.5 : 5.5} />
          <text className="trend-value" x={x(i)} y={y(p.value) - 13} textAnchor="middle">{p.value}%</text>
          <text className="trend-axis" x={x(i)} y={H - 10} textAnchor="middle">{p.label}</text>
        </g>
      ))}
    </svg>
  );
}
