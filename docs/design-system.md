# MediGuide design system

The reference for the public website (`frontend/src/app/site/`) and the signed-in workspace. Tokens live in `frontend/src/app/globals.css` as `--mg-*` custom properties.

## Principles

1. **Show the real product.** Visuals are rendered product UI with synthetic data, never stock photography or invented metrics.
2. **Evidence stays visible.** Wherever a value appears, its source (document, page, verification state) is one step away.
3. **Calm, not busy.** Motion explains a change of state (a chart drawing, a step completing). Nothing loops, bounces or spins.
4. **Honest labels.** Planned work is labelled *Planned*. Claims are limited to what the code does: no compliance badges, testimonials or certifications.

## Color

| Token | Value | Use |
|---|---|---|
| `--mg-forest` | `#103F35` | Headings, primary text on light, dark surfaces |
| `--mg-teal` | `#177C70` | Primary actions, links, focus (5.1:1 on white) |
| `--mg-teal-strong` | `#146B60` | Hover and pressed state for teal |
| `--mg-mint` | `#C8F1E3` | Highlights, selected states, text on dark surfaces (9.6:1 on forest) |
| `--mg-ivory` | `#F7F9F6` | Page background |
| `--mg-coral` | `#E58D79` | **Decorative only** (2.5:1 on white). Never used for text. |
| `--mg-coral-text` | `#A8482F` | Coral-toned text, such as "flagged on report" (5.8:1 on white, 5.0:1 on `--mg-coral-soft`) |
| `--mg-text` | `#13221E` | Body text |
| `--mg-text-muted` | `#4F5F59` | Secondary text (6.7:1 on white) |
| `--mg-border` | `#DCE5E0` | Hairlines and card borders |
| `--mg-surface` | `#FFFFFF` | Cards |
| `--mg-surface-dark` | `#0B2A23` | Dark sections; text on it uses mint and `#E8F3EE` |

All text pairs meet WCAG 2.2 AA (4.5:1 for body text, 3:1 for large text and UI). Status is never shown by color alone: every chip also has an icon or a word.

## Type

- **Sans:** Plus Jakarta Sans (already loaded via `next/font`) for UI and display. Display headings use weight 700 with tight tracking (−0.035em).
- **Serif accent:** Source Serif 4 italic, used sparingly for one emphasised phrase per section heading.
- **Fluid scale (`clamp`):** display 44→76px, h2 32→52px, h3 20→24px, body 16–18px, small 13–14px.

## Space, shape and depth

- 8px spacing grid. Sections use 96–144px vertical padding on desktop and 64–80px on mobile.
- Content width is 1200px, with 24px gutters (16px under 480px).
- Radius: 10px for controls, 16px for cards, 24px for large showcase frames.
- Shadows have three soft, low-alpha forest-tinted levels (`--mg-shadow-1…3`). Depth comes from layering, not heavy drop shadows.

## Motion

- Only `transform` and `opacity` are animated. Easing is `cubic-bezier(.2,.7,.2,1)`, 400–700ms.
- Scroll reveals use one shared IntersectionObserver. Content is visible without JavaScript and is hidden for reveal only once the observer is ready.
- `prefers-reduced-motion: reduce` turns off reveals, chart drawing and slide transitions. Content appears in its final state.
- The carousel never autoplays.

## Components (site)

`SiteHeader` (sticky, blurred after scroll, accessible mobile sheet) · `Hero` · `HeroVisual` (document preview + trend chart + verification card) · `WorkflowScroll` (Upload → Extract → Verify → Explain → Trace source) · `FeatureCarousel` · `BentoGrid` · `ImagingShowcase` · `TrustSection` · `FinalCta` · `SiteFooter`.

## Accessibility checklist

- Visible focus ring: 3px teal outline at 2px offset.
- Every interactive element is reachable and operable by keyboard. The carousel supports arrow keys, the mobile menu closes with Escape and returns focus.
- Headings are in order. Landmarks: `header`, `nav`, `main`, `footer`.
- Decorative visuals are `aria-hidden`. Rendered UI mockups carry a text label that describes them.
- Touch targets are at least 44×44px.
