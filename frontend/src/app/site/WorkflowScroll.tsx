"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { BadgeCheck, BookOpen, Check, CloudUpload, FileSearch, MessageSquareText, Pencil, ScanText, X } from "lucide-react";
import { REPORT_ROWS } from "./data";

type Step = { key: string; label: string; title: string; body: string; icon: typeof CloudUpload; visual: ReactNode };

function UploadVisual() {
  return (
    <div className="wf-panel">
      <div className="wf-file">
        <span className="wf-file-icon"><CloudUpload size={18} /></span>
        <div>
          <strong>sample-lab-report.pdf</strong>
          <small>3 pages · PDF</small>
        </div>
      </div>
      <ol className="wf-checklist">
        <li className="is-done"><Check size={13} /> Upload complete</li>
        <li className="is-done"><Check size={13} /> File validated</li>
        <li className="is-active"><span className="wf-dot" /> Reading document</li>
      </ol>
      <p className="wf-note">The original file is kept, so every value can link back to it.</p>
    </div>
  );
}

function ExtractVisual() {
  return (
    <div className="wf-panel">
      <p className="wf-panel-title">Information found · page 3</p>
      <div className="wf-table">
        {REPORT_ROWS.slice(0, 4).map((row, i) => (
          <div key={row.test} className="wf-row">
            <span>{row.test}</span>
            <span className="wf-mono">{row.value} {row.unit}</span>
            <span className={i === 3 ? "wf-chip wf-chip-amber" : "wf-chip"}>{i === 3 ? "Needs review" : "Clearly visible"}</span>
          </div>
        ))}
      </div>
      <p className="wf-note">Text PDFs are read directly. Photos and scans use a local vision model.</p>
    </div>
  );
}

function VerifyVisual() {
  return (
    <div className="wf-panel">
      <div className="wf-verify-field">
        <div className="wf-verify-top">
          <strong>Hemoglobin A1C</strong>
          <span className="wf-chip">Clearly visible</span>
        </div>
        <div className="wf-input">6.7 <small>%</small></div>
        <div className="wf-actions">
          <span className="wf-action is-on"><Check size={13} /> Confirm</span>
          <span className="wf-action"><Pencil size={13} /> Edit</span>
          <span className="wf-action"><X size={13} /> Reject</span>
        </div>
      </div>
      <p className="wf-confirmed"><BadgeCheck size={15} /> Nothing is saved to your records until you confirm it.</p>
    </div>
  );
}

function ExplainVisual() {
  return (
    <div className="wf-panel">
      <p className="wf-panel-title">Understanding this result</p>
      <p className="wf-prose">
        Your report lists Hemoglobin A1C at 6.7%, above its printed range of under 5.7% <span className="wf-cite wf-cite-doc">D3</span>.
        A1C reflects average blood sugar over roughly the past three months <span className="wf-cite">1</span>.
      </p>
      <div className="wf-sources">
        <span><FileSearch size={13} /> D3 · your report, page 3</span>
        <span><BookOpen size={13} /> 1 · approved educational source</span>
      </div>
      <p className="wf-note">Educational, not a diagnosis. Questions to bring to your clinician come with it.</p>
    </div>
  );
}

function TraceVisual() {
  return (
    <div className="wf-panel wf-trace">
      <div className="wf-page">
        <p className="wf-page-title">Synthetic Lab Report · page 3</p>
        {REPORT_ROWS.map((row, i) => (
          <div key={row.test} className={i === 0 ? "wf-page-row is-source" : "wf-page-row"}>
            <span>{row.test}</span>
            <span>{row.value} {row.unit}</span>
          </div>
        ))}
      </div>
      <p className="wf-note"><ScanText size={13} /> Opened at the exact page, with the value highlighted.</p>
    </div>
  );
}

const STEPS: Step[] = [
  {
    key: "upload", label: "Upload", icon: CloudUpload, visual: <UploadVisual />,
    title: "Add a report the way you received it.",
    body: "Lab PDFs, phone photos of printed reports, radiology reports and medication labels. Your original upload is kept exactly as it is.",
  },
  {
    key: "extract", label: "Extract", icon: ScanText, visual: <ExtractVisual />,
    title: "Values, units and ranges, pulled out for you.",
    body: "MediGuide reads each test with its unit and the reference range printed on the report, and marks anything that was hard to read so you look at it first.",
  },
  {
    key: "verify", label: "Verify", icon: BadgeCheck, visual: <VerifyVisual />,
    title: "You confirm every value before it counts.",
    body: "Confirm, correct or reject each field. Only reviewed values reach your timeline, and once a report is confirmed it isn't silently overwritten.",
  },
  {
    key: "explain", label: "Explain", icon: MessageSquareText, visual: <ExplainVisual />,
    title: "Plain-language context, with sources.",
    body: "Explanations separate what your report says from general health information, cite approved educational sources, and never diagnose or recommend treatment.",
  },
  {
    key: "trace", label: "Trace source", icon: FileSearch, visual: <TraceVisual />,
    title: "One tap back to the original page.",
    body: "Every trend point, search result and explanation opens the page it came from with the value highlighted, so you can check it against the original any time.",
  },
];

export function WorkflowScroll() {
  const [active, setActive] = useState(0);
  const stepRefs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    if (!("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(Number((entry.target as HTMLElement).dataset.index));
        }
      },
      // A step becomes active as it crosses the middle band of the screen.
      { rootMargin: "-45% 0px -45% 0px" },
    );
    stepRefs.current.forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return (
    <div className="workflow">
      <div className="workflow-stage" aria-hidden="true">
        <ol className="workflow-rail">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            return (
              <li key={step.key} className={i === active ? "is-active" : i < active ? "is-done" : ""}>
                <span><Icon size={15} /></span>
                {step.label}
              </li>
            );
          })}
        </ol>
        <div className="workflow-visuals">
          {STEPS.map((step, i) => (
            <div key={step.key} className={i === active ? "workflow-visual is-active" : "workflow-visual"}>
              {step.visual}
            </div>
          ))}
        </div>
      </div>

      <ol className="workflow-steps">
        {STEPS.map((step, i) => (
          <li
            key={step.key}
            ref={(el) => { stepRefs.current[i] = el; }}
            data-index={i}
            className={i === active ? "workflow-step is-active" : "workflow-step"}
          >
            <p className="workflow-step-label"><span>{String(i + 1).padStart(2, "0")}</span>{step.label}</p>
            <h3>{step.title}</h3>
            <p>{step.body}</p>
            <div className="workflow-step-visual" aria-hidden="true">{step.visual}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}
