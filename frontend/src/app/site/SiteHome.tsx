import { FeatureCarousel } from "./FeatureCarousel";
import { RevealObserver } from "./RevealObserver";
import { SiteHeader } from "./SiteHeader";
import { WorkflowScroll } from "./WorkflowScroll";
import {
  BentoGrid, FinalCta, Hero, ImagingShowcase, ProofStrip, SectionHeading, SiteFooter, TrustSection,
} from "./sections";
import "./site.css";

/** The public homepage. Server-rendered; only the header, carousel,
 * workflow and reveal observer ship JavaScript. */
export function SiteHome() {
  return (
    <div className="site">
      <a href="#main" className="skip-link">Skip to content</a>
      <div id="top-sentinel" aria-hidden="true" />
      <SiteHeader />
      <main id="main">
        <Hero />
        <ProofStrip />

        <section className="site-section" id="workflow" aria-labelledby="workflow-title">
          <div className="site-container">
            <SectionHeading
              id="workflow-title"
              eyebrow="How it works"
              title="From a stack of reports to answers"
              accent="you can check."
              body="Five steps, and you stay in control of each one."
            />
            <WorkflowScroll />
          </div>
        </section>

        <section className="site-section site-section-tint" id="features" aria-labelledby="features-title">
          <div className="site-container">
            <SectionHeading
              id="features-title"
              eyebrow="Features"
              title="One place for the documents"
              accent="your care produces."
            />
            <FeatureCarousel />
          </div>
        </section>

        <section className="site-section" id="product" aria-labelledby="product-title">
          <div className="site-container">
            <SectionHeading
              id="product-title"
              eyebrow="Built around evidence"
              title="Every answer keeps"
              accent="its receipts."
              body="MediGuide is designed so you can always see where information came from, and who confirmed it."
            />
            <BentoGrid />
          </div>
        </section>

        <section className="site-section site-section-tint" id="imaging" aria-labelledby="imaging-title">
          <div className="site-container">
            <SectionHeading
              id="imaging-title"
              eyebrow="Imaging report intelligence"
              title="Radiology reports,"
              accent="made readable."
              body="MediGuide works from the radiologist's written report. It does not look at or interpret the images themselves."
            />
            <ImagingShowcase />
          </div>
        </section>

        <section className="site-section" id="trust" aria-labelledby="trust-title">
          <div className="site-container">
            <SectionHeading
              id="trust-title"
              eyebrow="Trust & safety"
              title="Clear about what it does,"
              accent="and what it doesn't."
            />
            <TrustSection />
          </div>
        </section>

        <FinalCta />
      </main>
      <SiteFooter />
      <RevealObserver />
    </div>
  );
}
