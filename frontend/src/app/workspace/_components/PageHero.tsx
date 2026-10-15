import Image, { type StaticImageData } from "next/image";
import type { CSSProperties, ReactNode } from "react";
import reviewPhoto from "../../../../public/images/site/person-tablet-review.webp";
import consultPhoto from "../../../../public/images/site/hero-consult.webp";
import labPhoto from "../../../../public/images/site/hero-lab.webp";
import medicinePhoto from "../../../../public/images/site/hero-medicine.webp";

/**
 * Photography is reserved for the workspace home; data-heavy pages use the
 * compact band so the information starts higher on the screen.
 */
export const HERO_PHOTOS = {
  home: [reviewPhoto, consultPhoto, labPhoto, medicinePhoto],
} satisfies Record<string, StaticImageData[]>;

export type HeroPhotoKey = keyof typeof HERO_PHOTOS;

type PageHeroProps = {
  eyebrow: string;
  title: ReactNode;
  /** Trailing words of the title, set in champagne like the homepage headline. */
  accent?: string;
  lead?: ReactNode;
  /** Buttons and controls; forest/quiet buttons are restyled for the dark band. */
  actions?: ReactNode;
  /** Small status pills shown top-right (e.g. "Human review first"). */
  meta?: ReactNode;
  /** Background photography; several photos crossfade like the homepage hero. */
  photo?: HeroPhotoKey;
  className?: string;
};

function delay(ms: number) {
  return { style: { "--rise-delay": `${ms}ms` } as CSSProperties };
}

/** Dark brand band that opens every workspace page, matching the public homepage hero. */
export function PageHero({ eyebrow, title, accent, lead, actions, meta, photo, className = "" }: PageHeroProps) {
  const photos = photo ? HERO_PHOTOS[photo] : [];
  const slideshow = photos.length > 1;
  return (
    <header className={`page-hero ${photos.length ? "has-photo" : "is-compact"} ${className}`.trim()}>
      {photos.length ? (
        <div className="page-hero-media" aria-hidden="true">
          {photos.map((image, i) => (
            <div
              key={image.src}
              className={slideshow ? "page-hero-slide is-cycling" : "page-hero-slide"}
              style={{ "--slide": i } as CSSProperties}
            >
              <Image src={image} alt="" fill sizes="(max-width: 800px) 100vw, 1100px" priority={i === 0} placeholder="blur" />
            </div>
          ))}
        </div>
      ) : null}
      <div className="page-hero-body">
        <div className="page-hero-text">
          <p className="page-hero-eyebrow ws-rise-down" {...delay(0)}><span aria-hidden="true" />{eyebrow}</p>
          <h2>
            <span className="ws-rise" {...delay(110)}>{title}</span>
            {accent ? <> <span className="page-hero-accent ws-rise" {...delay(240)}>{accent}</span></> : null}
          </h2>
          {lead ? <p className="page-hero-lead ws-rise-left" {...delay(360)}>{lead}</p> : null}
        </div>
        {meta ? <div className="page-hero-meta ws-rise-right" {...delay(300)}>{meta}</div> : null}
      </div>
      {actions ? <div className="page-hero-actions ws-rise" {...delay(480)}>{actions}</div> : null}
    </header>
  );
}
