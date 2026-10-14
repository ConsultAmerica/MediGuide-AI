import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight, BadgeCheck, BookOpen, Check, ClipboardList, FileSearch, FileText, Lock, MessageCircleQuestion,
  Pill, ScanLine, ShieldCheck, Trash2, TrendingUp, X,
} from "lucide-react";
import { BrandLogo } from "../brand-logo";
import { MRI_REPORT, REPORT_ROWS } from "./data";
import { HeroVisual } from "./HeroVisual";
import { TrendChart } from "./TrendChart";
import reportPhoto from "../../../public/images/site/person-report-laptop.webp";
import medicationPhoto from "../../../public/images/site/person-medication-label.webp";

const DEMO_HREF = "/workspace/documents?action=sample";

export function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero-backdrop" aria-hidden="true" />
      <div className="site-container hero-grid">
        <div className="hero-copy">
          <p className="eyebrow eyebrow-on-band"><span className="eyebrow-dot" aria-hidden="true" />Health document intelligence</p>
          <h1 id="hero-title">
            Your health information. <span className="hero-accent">Finally connected.</span>
          </h1>
          <p className="hero-lead">
            Turn medical reports into verified, understandable information with connected timelines,
            grounded explanations and direct links to original evidence.
          </p>
          <div className="hero-actions">
            <Link href={DEMO_HREF} className="site-btn site-btn-lime site-btn-lg" prefetch={false}>
              Try it with synthetic data <ArrowRight size={17} aria-hidden="true" />
            </Link>
            <a href="#workflow" className="site-btn site-btn-outline-light site-btn-lg">See how it works</a>
          </div>
          <p className="hero-note">
            <ShieldCheck size={15} aria-hidden="true" /> No sign-up needed for the demo · Synthetic data only · Educational, not diagnostic
          </p>
        </div>
        <HeroVisual />
      </div>
      <div className="site-container">
        <StatsStrip />
      </div>
    </section>
  );
}

/** Every figure here is a property of the product, not a usage metric. */
function StatsStrip() {
  const stats = [
    { value: "12", label: "Common lab tests tracked across all your reports" },
    { value: "5", label: "Imaging types organised, from X-ray to PET-CT" },
    { value: "0", label: "Values saved to your records before you confirm them" },
    { value: "1 tap", label: "From any result back to its original page" },
  ];
  return (
    <dl className="stats">
      {stats.map((stat) => (
        <div key={stat.label} className="stat">
          <dt>{stat.label}</dt>
          <dd>{stat.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function IconStrip() {
  const items = [
    { icon: FileText, label: "Document intelligence" },
    { icon: TrendingUp, label: "Lab trends" },
    { icon: ScanLine, label: "Imaging reports" },
    { icon: Pill, label: "Medication labels" },
    { icon: MessageCircleQuestion, label: "Ask MediGuide" },
    { icon: ClipboardList, label: "Visit preparation" },
  ];
  return (
    <nav className="icon-strip" aria-label="Features">
      <ul className="site-container">
        {items.map(({ icon: Icon, label }) => (
          <li key={label}>
            <a href="#features">
              <span className="icon-strip-icon"><Icon size={20} aria-hidden="true" /></span>
              {label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function FeatureCards() {
  return (
    <div className="feature-cards">
      <article className="feature-card" data-reveal>
        <div className="feature-card-media">
          <Image
            src={reportPhoto}
            alt="A man at his kitchen table comparing a printed lab report with his laptop"
            sizes="(max-width: 760px) 92vw, (max-width: 1080px) 46vw, 380px"
            placeholder="blur"
          />
        </div>
        <div className="feature-card-body">
          <p className="feature-card-kicker"><FileText size={15} aria-hidden="true" /> Lab reports</p>
          <h3>Read every value, with its page beside it.</h3>
          <p>Upload a PDF or a photo and review each test, unit and printed range before anything is saved.</p>
          <Link href={DEMO_HREF} className="site-link-arrow" prefetch={false}>Try the sample report <ArrowRight size={15} aria-hidden="true" /></Link>
        </div>
      </article>

      <article className="feature-card feature-card-ui" data-reveal>
        <div className="feature-card-media feature-card-chart" aria-hidden="true">
          <div className="feature-chart-frame">
            <p className="feature-chart-title">Hemoglobin A1C <span>3 reports</span></p>
            <TrendChart />
          </div>
        </div>
        <div className="feature-card-body">
          <p className="feature-card-kicker"><TrendingUp size={15} aria-hidden="true" /> Lab trends</p>
          <h3>See how a result changes across reports.</h3>
          <p>Confirmed values line up by test and date, each against the range its own report printed.</p>
          <Link href="/workspace/labs" className="site-link-arrow" prefetch={false}>Open Labs <ArrowRight size={15} aria-hidden="true" /></Link>
        </div>
      </article>

      <article className="feature-card" data-reveal>
        <div className="feature-card-media">
          <Image
            src={medicationPhoto}
            alt="A man reading the label on a prescription bottle while looking at his laptop"
            sizes="(max-width: 760px) 92vw, (max-width: 1080px) 46vw, 380px"
            placeholder="blur"
          />
        </div>
        <div className="feature-card-body">
          <p className="feature-card-kicker"><Pill size={15} aria-hidden="true" /> Medications</p>
          <h3>Know exactly what the label says.</h3>
          <p>Photograph a pharmacy label, confirm the name, strength and directions, then learn about it.</p>
          <Link href="/workspace/medications" className="site-link-arrow" prefetch={false}>Open Medications <ArrowRight size={15} aria-hidden="true" /></Link>
        </div>
      </article>
    </div>
  );
}

export function SectionHeading({ eyebrow, title, accent, body, id, centered = false }: { eyebrow: string; title: string; accent?: string; body?: string; id?: string; centered?: boolean }) {
  return (
    <div className={centered ? "section-heading is-centered" : "section-heading"} data-reveal>
      <p className="eyebrow">{eyebrow}</p>
      <h2 id={id}>{title}{accent ? <> <span className="heading-accent">{accent}</span></> : null}</h2>
      {body && <p className="section-lead">{body}</p>}
    </div>
  );
}

export function BentoGrid() {
  return (
    <div className="bento">
      <article className="bento-card bento-trend" data-reveal>
        <div className="bento-copy">
          <p className="bento-kicker">Lab trends</p>
          <h3>Results from different reports, finally side by side.</h3>
          <p>Each point is a value you confirmed, shown against the range its own report printed.</p>
        </div>
        <div className="bento-chart">
          {/* The wide chart keeps readable text on large cards; phones get the compact one. */}
          <div className="chart-wide-only"><TrendChart size="wide" /></div>
          <div className="chart-compact-only"><TrendChart /></div>
        </div>
        <div className="bento-legend" aria-hidden="true">
          <span><i className="legend-line" /> Your confirmed results</span>
          <span><i className="legend-band" /> Printed reference range</span>
        </div>
      </article>

      <article className="bento-card bento-verify" data-reveal>
        <p className="bento-kicker">Human verification</p>
        <h3>Reviewed by you, value by value.</h3>
        <div className="bento-fields" aria-hidden="true">
          {REPORT_ROWS.map((row, i) => (
            <div key={row.test} className={i === 4 ? "bento-field is-pending" : "bento-field"}>
              <span className={i < 4 ? "tick is-on" : "tick"}>{i < 4 ? <Check size={12} /> : null}</span>
              <span>{row.test}</span>
              <strong>{row.value} <small>{row.unit}</small></strong>
            </div>
          ))}
        </div>
        <div className="bento-confirm" aria-hidden="true">
          <span>4 of 5 reviewed</span>
          <span className="bento-confirm-btn">Confirm reviewed items <Check size={14} /></span>
        </div>
      </article>

      <article className="bento-card bento-imaging" data-reveal>
        <div className="bento-copy">
          <p className="bento-kicker">Imaging reports</p>
          <h3>The radiologist&apos;s words, organised and explained.</h3>
        </div>
        <div className="bento-report" aria-hidden="true">
          <p><b>IMPRESSION</b> {MRI_REPORT.impression}</p>
          <div className="bento-arrow"><ArrowRight size={16} /></div>
          <ul>
            {MRI_REPORT.findingsList.slice(0, 2).map((f) => <li key={f.text}><BadgeCheck size={13} /> {f.text}</li>)}
          </ul>
        </div>
      </article>

      <article className="bento-card bento-source" data-reveal>
        <p className="bento-kicker">Source evidence</p>
        <h3>Tap a value, see its page.</h3>
        <div className="bento-trace" aria-hidden="true">
          <span className="bento-value">6.7 %</span>
          <svg viewBox="0 0 80 24" className="bento-trace-line"><path d="M2 12 H70" /><path d="M64 6 L72 12 L64 18" /></svg>
          <span className="bento-page"><FileText size={14} /> Page 3</span>
        </div>
      </article>

      <article className="bento-card bento-dark" data-reveal>
        <p className="bento-kicker">Private by design</p>
        <h3>Only your account can open your records.</h3>
        <ul className="bento-list">
          <li><Lock size={14} aria-hidden="true" /> Each record belongs to one account</li>
          <li><Trash2 size={14} aria-hidden="true" /> Delete a document and everything read from it</li>
        </ul>
      </article>
    </div>
  );
}

export function ImagingShowcase() {
  return (
    <div className="imaging-show" data-reveal>
      <div className="imaging-report">
        <div className="imaging-report-bar">
          <ScanLine size={15} aria-hidden="true" />
          <span>Original report · page 1</span>
          <em>Synthetic</em>
        </div>
        <div className="imaging-report-body">
          <p className="imaging-report-title">{MRI_REPORT.title}</p>
          <p className="imaging-report-date">{MRI_REPORT.date}</p>
          <p><b>EXAM</b> {MRI_REPORT.exam}</p>
          <p><b>FINDINGS</b> {MRI_REPORT.findings}</p>
          <p className="is-source"><b>IMPRESSION</b> {MRI_REPORT.impression}</p>
        </div>
      </div>

      <div className="imaging-panels">
        <div className="imaging-panel">
          <p className="imaging-panel-title">Structured findings</p>
          <ul className="imaging-findings">
            {MRI_REPORT.findingsList.map((f) => (
              <li key={f.text}>
                <span>{f.text}<small>{f.section}</small></span>
                <span className={f.state.startsWith("Confirmed") ? "chip-ok" : "chip-wait"}>
                  {f.state.startsWith("Confirmed") ? <Check size={12} aria-hidden="true" /> : null}{f.state}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="imaging-panel">
          <p className="imaging-panel-title">Understanding &ldquo;joint effusion&rdquo;</p>
          <p className="imaging-label">From your report</p>
          <p className="imaging-text">The impression notes a <mark>small joint effusion</mark> in the right knee.</p>
          <p className="imaging-label">General health information</p>
          <p className="imaging-text">
            A joint effusion is extra fluid within a joint. It can be associated with injury, overuse or
            inflammation <span className="wf-cite">1</span>.
          </p>
          <div className="imaging-links">
            <span><FileSearch size={14} aria-hidden="true" /> Open source page</span>
            <span><BookOpen size={14} aria-hidden="true" /> 1 approved source</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function TrustSection() {
  const does = [
    "Reads the text of reports you upload, and shows where each value came from",
    "Waits for you to confirm values before saving them to your records",
    "Explains results and terms using an approved educational library, with citations",
    "Keeps your original files so you can always check the source",
  ];
  const doesNot = [
    "Diagnose conditions or interpret scan images. It works from the written report only",
    "Recommend treatment, medication or dose changes",
    "Replace your clinician. Questions it suggests are for your appointment",
    "Process DICOM imaging files",
  ];
  return (
    <div className="trust-grid">
      <div className="trust-col" data-reveal>
        <h3><span className="trust-icon trust-yes"><Check size={16} aria-hidden="true" /></span>What MediGuide does</h3>
        <ul>{does.map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
      <div className="trust-col" data-reveal>
        <h3><span className="trust-icon trust-no"><X size={16} aria-hidden="true" /></span>What it will not do</h3>
        <ul>{doesNot.map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
      <p className="trust-note" data-reveal>
        MediGuide is an educational project and is not a medical device. The public demo runs on synthetic
        data. Please don&apos;t upload real health records to it. In an emergency, contact your local emergency services.
      </p>
    </div>
  );
}

export function FinalCta() {
  return (
    <section className="final-cta" aria-labelledby="final-cta-title">
      <div className="site-container final-cta-inner" data-reveal>
        <div className="final-cta-copy">
          <p className="eyebrow eyebrow-on-band">Try it in about a minute</p>
          <h2 id="final-cta-title">See your reports become <span className="hero-accent">something you can follow.</span></h2>
          <p>Load the synthetic three-report sample, review it, and follow a value back to its page.</p>
          <div className="hero-actions">
            <Link href={DEMO_HREF} className="site-btn site-btn-lime site-btn-lg" prefetch={false}>
              Try it with synthetic data <ArrowRight size={17} aria-hidden="true" />
            </Link>
            <Link href="/signin?mode=register" className="site-btn site-btn-outline-light site-btn-lg" prefetch={false}>Create an account</Link>
          </div>
        </div>
        <div className="final-cta-card" aria-hidden="true">
          <p className="final-cta-card-title"><BadgeCheck size={16} /> Report confirmed</p>
          <ul>
            {REPORT_ROWS.slice(0, 3).map((row) => (
              <li key={row.test}><span>{row.test}</span><strong>{row.value} {row.unit}</strong></li>
            ))}
          </ul>
          <p className="final-cta-card-foot"><FileSearch size={14} /> Each value links to page 3</p>
        </div>
      </div>
    </section>
  );
}

export function SiteFooter() {
  const columns = [
    { title: "Product", links: [["How it works", "#workflow"], ["Features", "#features"], ["Imaging", "#imaging"], ["Trust & safety", "#trust"]] },
    { title: "Workspace", links: [["Documents", "/workspace/documents"], ["Labs", "/workspace/labs"], ["Imaging", "/workspace/imaging"], ["Visit Preparation", "/workspace/visit"]] },
    { title: "Account", links: [["Sign in", "/signin"], ["Create an account", "/signin?mode=register"], ["System status", "/workspace/system"]] },
  ];
  return (
    <footer className="site-footer">
      <div className="site-container footer-grid">
        <div className="footer-brand">
          <BrandLogo variant="wordmark" />
          <p>Health document intelligence: verified results, connected over time, with the evidence still attached.</p>
        </div>
        {columns.map((column) => (
          <nav key={column.title} aria-label={column.title} className="footer-col">
            <p>{column.title}</p>
            <ul>
              {column.links.map(([label, href]) => (
                <li key={label}>
                  {href.startsWith("#") ? <a href={href}>{label}</a> : <Link href={href} prefetch={false}>{label}</Link>}
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="site-container footer-base">
        <p>Educational information only. Not a diagnosis or a substitute for professional medical advice.</p>
        <p>© 2026 MediGuide</p>
      </div>
    </footer>
  );
}
