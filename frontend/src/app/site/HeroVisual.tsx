import { ArrowUpRight, BadgeCheck, TrendingUp } from "lucide-react";
import { TrendChart } from "./TrendChart";

/**
 * The two MediGuide cards that matter most, floating over the hero
 * slideshow: the trend built from a person's reports, and the verification
 * that ties a value to its source page. Rendered UI with synthetic data.
 */
export function HeroVisual() {
  return (
    <div className="hero-visual">
      <div className="hero-stage" aria-hidden="true" />

      <div className="hv-card hv-trend" aria-hidden="true">
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

      <div className="hv-card hv-verify" aria-hidden="true">
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
