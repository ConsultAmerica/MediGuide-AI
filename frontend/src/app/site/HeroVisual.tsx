import { ArrowUpRight, BadgeCheck, FileText, TrendingUp } from "lucide-react";
import { REPORT_DATE, REPORT_ROWS } from "./data";
import { TrendChart } from "./TrendChart";

/**
 * Rendered product UI, not a screenshot: the synthetic report page, the lab
 * trend MediGuide builds from it, and the verification card that ties a
 * value back to its exact line. Purely illustrative, so hidden from
 * assistive tech; the hero copy carries the meaning.
 */
export function HeroVisual() {
  return (
    <div className="hero-visual" aria-hidden="true">
      <div className="hero-glow" />

      <div className="hv-card hv-doc">
        <div className="hv-doc-bar">
          <FileText size={14} />
          <span>sample-lab-report.pdf</span>
          <em>Page 3 of 3</em>
        </div>
        <div className="hv-doc-page">
          <p className="hv-doc-title">Synthetic Lab Report</p>
          <p className="hv-doc-meta">Collection date: {REPORT_DATE}</p>
          <div className="hv-doc-table">
            {REPORT_ROWS.map((row, i) => (
              <div key={row.test} className={i === 0 ? "hv-doc-row is-source" : "hv-doc-row"}>
                <span>{row.test}</span>
                <span>{row.value} {row.unit}</span>
                <span>{row.range}</span>
                <span className="hv-flag">{row.flag}</span>
              </div>
            ))}
          </div>
          <div className="hv-doc-lines">
            <i /><i /><i />
          </div>
        </div>
      </div>

      <div className="hv-card hv-trend">
        <div className="hv-card-head">
          <span className="hv-icon"><TrendingUp size={14} /></span>
          <div>
            <p className="hv-kicker">A1C trend</p>
            <p className="hv-big">6.7<small>%</small></p>
          </div>
          <span className="hv-chip hv-chip-coral">Flagged on report</span>
        </div>
        <TrendChart animateOnLoad />
        <p className="hv-foot">3 verified results · 3 reports</p>
      </div>

      <div className="hv-card hv-verify">
        <div className="hv-verify-head">
          <BadgeCheck size={16} />
          <span>Verified by you</span>
        </div>
        <p className="hv-verify-value">Hemoglobin A1C · 6.7 %</p>
        <div className="hv-source-line">
          <span>Source · page 3</span>
          <code>Hemoglobin A1C 6.7 % Ref &lt;5.7</code>
        </div>
        <p className="hv-link">Open source page <ArrowUpRight size={13} /></p>
      </div>
    </div>
  );
}
