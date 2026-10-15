/* eslint-disable @next/next/no-img-element */

/**
 * Official MediGuide branding, rendered from the approved logo artwork.
 *
 * The emblem and the custom serif lettering are raster extractions of the
 * approved board (public/brand/*.webp), not redrawn or re-typeset, so their
 * shapes stay exactly as designed. Each asset has a transparent background:
 *
 *   tone "dark"  : ivory "Medi" + champagne "Guide", for aubergine surfaces
 *   tone "light" : aubergine "Medi" + champagne "Guide", for ivory/white
 */

type BrandVariant = "mark" | "wordmark" | "full";
type BrandTone = "dark" | "light";

type BrandLogoProps = {
  className?: string;
  /** mark = emblem only; wordmark = emblem + MediGuide; full = with tagline */
  variant?: BrandVariant;
  /** Surface the logo sits on. */
  tone?: BrandTone;
  priority?: boolean;
};

const TAGLINE = "HEALTH DOCUMENT INTELLIGENCE";

const ASSETS = {
  dark: {
    wordmark: { src: "/brand/mediguide-logo-dark.webp", width: 760, height: 205 },
    full: { src: "/brand/mediguide-logo-dark-tagline.webp", width: 760, height: 205 },
  },
  light: {
    wordmark: { src: "/brand/mediguide-logo-light.webp", width: 607, height: 177 },
    full: { src: "/brand/mediguide-logo-light-tagline.webp", width: 607, height: 177 },
  },
  mark: { src: "/brand/mediguide-emblem.webp", width: 256, height: 252 },
} as const;

/** The circular emblem on its own (compact navigation, icon-only spots). */
export function BrandMark({ className = "", title = "MediGuide" }: { className?: string; title?: string }) {
  const { src, width, height } = ASSETS.mark;
  return (
    <img className={`brand-mark-img ${className}`.trim()} src={src} width={width} height={height} alt={title} decoding="async" />
  );
}

export function BrandLogo({ className = "", variant = "wordmark", tone = "dark", priority = false }: BrandLogoProps) {
  if (variant === "mark") {
    return <BrandMark className={className} />;
  }
  const asset = ASSETS[tone][variant];
  return (
    <img
      className={`brand-logo brand-logo-${variant} brand-logo-${tone} ${className}`.trim()}
      src={asset.src}
      width={asset.width}
      height={asset.height}
      alt={variant === "full" ? `MediGuide — ${TAGLINE}` : "MediGuide"}
      decoding="async"
      {...(priority ? { fetchPriority: "high" as const } : {})}
    />
  );
}

export const MEDIGUIDE_TAGLINE = TAGLINE;
