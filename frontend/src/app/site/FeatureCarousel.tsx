"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";
import Link from "next/link";
import {
  ArrowRight, BadgeCheck, ChevronLeft, ChevronRight, ClipboardList, FileText,
  MessageCircleQuestion, Pill, ScanLine, TrendingUp,
} from "lucide-react";
import { MRI_REPORT, REPORT_ROWS } from "./data";
import { TrendChart } from "./TrendChart";

type Slide = {
  key: string;
  name: string;
  icon: typeof FileText;
  status: string;
  statusTone: "ready" | "local" ;
  title: string;
  body: string;
  points: string[];
  href: string;
  cta: string;
  planned?: string;
  visual: ReactNode;
};

const SLIDES: Slide[] = [
  {
    key: "documents", name: "Document Intelligence", icon: FileText, status: "Available", statusTone: "ready",
    title: "Lab reports, read and laid out for review.",
    body: "Upload a PDF or a photo. MediGuide finds each test, its value, unit and printed range, and shows you the page it came from.",
    points: ["Text PDFs read without any AI model", "Hard-to-read values flagged for review", "Original file and page previews kept"],
    href: "/workspace/documents?action=sample", cta: "Try the synthetic report",
    visual: (
      <div className="fc-mock">
        {REPORT_ROWS.slice(0, 3).map((row, i) => (
          <div key={row.test} className="fc-field">
            <span>{row.test}</span>
            <strong>{row.value} {row.unit}</strong>
            <span className={i === 2 ? "fc-chip is-amber" : "fc-chip"}>{i === 2 ? "Needs review" : "Clearly visible"}</span>
          </div>
        ))}
      </div>
    ),
  },
  {
    key: "labs", name: "Lab Trends", icon: TrendingUp, status: "Available", statusTone: "ready",
    title: "Every confirmed result, on one timeline.",
    body: "Confirmed values from separate reports line up by test, with each report's own printed range and a link back to every source page.",
    points: ["Trends across reports and dates", "Flags exactly as printed on each report", "Export to CSV or add to a visit"],
    href: "/workspace/labs", cta: "Open Labs",
    visual: <div className="fc-mock fc-mock-chart"><TrendChart /></div>,
  },
  {
    key: "imaging", name: "Imaging Reports", icon: ScanLine, status: "Available", statusTone: "ready",
    title: "Radiology reports, in plain language.",
    body: "MediGuide organises X-ray, CT, MRI, ultrasound and PET-CT reports by study, turns the radiologist's findings into a reviewable list, and explains terms.",
    points: ["Works from the written report only", "Findings verified by you before explanation", "Compare two confirmed reports"],
    href: "/workspace/imaging", cta: "Open Imaging",
    visual: (
      <div className="fc-mock">
        <p className="fc-mock-title">{MRI_REPORT.title}</p>
        {MRI_REPORT.findingsList.slice(0, 2).map((finding) => (
          <div key={finding.text} className="fc-finding"><BadgeCheck size={14} /> {finding.text}</div>
        ))}
      </div>
    ),
  },
  {
    key: "medications", name: "Medication Information", icon: Pill, status: "Uses a local AI model", statusTone: "local",
    title: "Read a medication label, then learn about it.",
    body: "Photograph a pharmacy label or type it in. MediGuide reads the name, strength and directions for you to confirm, then shares approved educational information.",
    points: ["Name, strength and directions as printed", "Nothing saved until you confirm", "Never suggests dose changes"],
    href: "/workspace/medications", cta: "Open Medications",
    visual: (
      <div className="fc-mock">
        <div className="fc-field"><span>Medication</span><strong>Metformin</strong><span className="fc-chip">Clearly visible</span></div>
        <div className="fc-field"><span>Strength</span><strong>500 mg</strong><span className="fc-chip">Clearly visible</span></div>
        <div className="fc-field"><span>Directions</span><strong>1 tablet twice daily</strong><span className="fc-chip is-amber">Needs review</span></div>
      </div>
    ),
  },
  {
    key: "ask", name: "Ask MediGuide", icon: MessageCircleQuestion, status: "Uses a local AI model", statusTone: "local",
    title: "Health questions, answered with citations.",
    body: "Ask a general health question by typing or by voice. Answers come from an approved educational library, with the passages they rely on shown beside them.",
    points: ["Every claim cites a source", "Emergency language routes to urgent-care guidance", "Read aloud or translate the answer"],
    href: "/workspace/ask", cta: "Open Ask MediGuide",
    visual: (
      <div className="fc-mock">
        <p className="fc-bubble fc-bubble-user">What does an A1C test measure?</p>
        <p className="fc-bubble">It reflects average blood sugar over about the past three months <span className="wf-cite">1</span>.</p>
      </div>
    ),
  },
  {
    key: "visit", name: "Visit Preparation", icon: ClipboardList, status: "Available", statusTone: "ready",
    title: "Walk into your appointment prepared.",
    body: "Gather your concern, confirmed results and medications into a short summary with questions for your clinician, then copy, print or download it.",
    points: ["Questions suggested from your confirmed results", "Copy, print or download as text", "Kept in this browser tab while you work"],
    planned: "Planned: save visit plans to your account and choose exactly which records to include.",
    href: "/workspace/visit", cta: "Open Visit Preparation",
    visual: (
      <div className="fc-mock">
        <p className="fc-mock-title">Questions for my clinician</p>
        {["What does a rising A1C mean for me?", "Should I repeat this test, and when?", "Is the joint effusion something to watch?"].map((q) => (
          <div key={q} className="fc-question"><span /> {q}</div>
        ))}
      </div>
    ),
  },
];

function capitalize(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function FeatureCarousel() {
  const [index, setIndex] = useState(0);
  const pointerStart = useRef<number | null>(null);
  const count = SLIDES.length;
  const go = (next: number) => setIndex((next + count) % count);

  // The viewport takes the active slide's own height (animated in CSS).
  // Sizing every slide to the tallest one left large empty bands on tablet
  // and mobile, where slide heights differ by up to ~280px. Height changes
  // only follow a tab, arrow or swipe (there is no autoplay), so the page
  // below never moves on its own.
  const slideRefs = useRef<(HTMLElement | null)[]>([]);
  const [slideHeights, setSlideHeights] = useState<number[]>([]);
  const viewportHeight = slideHeights[index];
  useEffect(() => {
    const slides = slideRefs.current.filter((node): node is HTMLElement => Boolean(node));
    if (!slides.length) return;
    // Natural height = content span + padding, measured from the children,
    // so it can shrink again after a resize (slides themselves are stretched).
    const natural = (node: HTMLElement) => {
      const children = Array.from(node.children) as HTMLElement[];
      if (!children.length) return node.offsetHeight;
      const rects = children.map((child) => child.getBoundingClientRect());
      const span = Math.max(...rects.map((r) => r.bottom)) - Math.min(...rects.map((r) => r.top));
      const style = getComputedStyle(node);
      return Math.ceil(span + parseFloat(style.paddingTop) + parseFloat(style.paddingBottom));
    };
    const measure = () => setSlideHeights(slides.map(natural));
    measure();
    const observer = new ResizeObserver(measure);
    slides.forEach((node) => Array.from(node.children).forEach((child) => observer.observe(child)));
    return () => observer.disconnect();
  }, []);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowRight") { event.preventDefault(); go(index + 1); }
    if (event.key === "ArrowLeft") { event.preventDefault(); go(index - 1); }
  }
  function onPointerDown(event: PointerEvent) {
    if (event.pointerType !== "mouse") pointerStart.current = event.clientX;
  }
  function onPointerUp(event: PointerEvent) {
    if (pointerStart.current === null) return;
    const dx = event.clientX - pointerStart.current;
    pointerStart.current = null;
    if (Math.abs(dx) > 48) go(index + (dx < 0 ? 1 : -1));
  }

  const current = SLIDES[index];

  return (
    <div
      className="carousel"
      role="region"
      aria-roledescription="carousel"
      aria-label="MediGuide features"
      onKeyDown={onKeyDown}
    >
      <div className="carousel-tabs" role="tablist" aria-label="Choose a feature">
        {SLIDES.map((slide, i) => {
          const Icon = slide.icon;
          return (
            <button
              key={slide.key}
              type="button"
              role="tab"
              id={`feature-tab-${slide.key}`}
              aria-selected={i === index}
              aria-controls={`feature-slide-${slide.key}`}
              tabIndex={i === index ? 0 : -1}
              aria-label={slide.name}
              className={i === index ? "carousel-tab is-active" : "carousel-tab"}
              onClick={() => setIndex(i)}
            >
              <Icon size={16} aria-hidden="true" />
              <span>{slide.name}</span>
            </button>
          );
        })}
      </div>

      <div className="carousel-viewport" style={viewportHeight ? { height: viewportHeight } : undefined} onPointerDown={onPointerDown} onPointerUp={onPointerUp} onPointerCancel={() => { pointerStart.current = null; }}>
        <div className="carousel-track" style={{ transform: `translateX(-${index * 100}%)` }}>
          {SLIDES.map((slide, i) => (
            <article
              key={slide.key}
              ref={(node) => { slideRefs.current[i] = node; }}
              id={`feature-slide-${slide.key}`}
              role="tabpanel"
              aria-roledescription="slide"
              aria-labelledby={`feature-tab-${slide.key}`}
              className="carousel-slide"
              inert={i !== index}
            >
              <div className="carousel-copy">
                <span className={`status-pill status-${slide.statusTone}`}>{slide.status}</span>
                <h3>{slide.title}</h3>
                <p>{slide.body}</p>
                <ul>
                  {slide.points.map((point) => <li key={point}>{point}</li>)}
                </ul>
                {slide.planned && <p className="carousel-planned"><span className="status-pill status-planned">Planned</span>{capitalize(slide.planned.replace(/^Planned:\s*/, ""))}</p>}
                <Link href={slide.href} className="site-link-arrow" prefetch={false}>
                  {slide.cta} <ArrowRight size={15} aria-hidden="true" />
                </Link>
              </div>
              <div className="carousel-visual" aria-hidden="true">{slide.visual}</div>
            </article>
          ))}
        </div>
      </div>

      <div className="carousel-controls">
        <button type="button" className="carousel-arrow" onClick={() => go(index - 1)} aria-label="Previous feature">
          <ChevronLeft size={20} />
        </button>
        <p className="carousel-count" aria-live="polite" aria-atomic="true">
          <span className="sr-only">Feature </span>{index + 1} <span aria-hidden="true">/</span><span className="sr-only"> of </span> {count}
          <span className="sr-only">: {current.name}</span>
        </p>
        <button type="button" className="carousel-arrow" onClick={() => go(index + 1)} aria-label="Next feature">
          <ChevronRight size={20} />
        </button>
      </div>
    </div>
  );
}
