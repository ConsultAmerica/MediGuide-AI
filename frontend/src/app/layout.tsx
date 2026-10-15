import type { Metadata } from "next";
import { Instrument_Serif, Manrope } from "next/font/google";
import "./globals.css";

// Interface face for everything functional: navigation, forms, tables,
// values. Variable names are kept so existing stylesheets pick it up.
const landingSans = Manrope({
  variable: "--font-landing-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

// Editorial serif, used selectively for marketing headlines only. Preloaded
// because the homepage hero headline (the LCP element) is set in it.
const landingSerif = Instrument_Serif({
  variable: "--font-landing-serif",
  subsets: ["latin"],
  weight: ["400"],
  style: ["normal", "italic"],
});

const DESCRIPTION =
  "Health document intelligence that converts uploaded lab reports into structured, traceable timelines and understandable educational explanations while preserving source evidence.";

export const metadata: Metadata = {
  // Without this, Next resolves the OG/Twitter image to a relative path
  // against "http://localhost:3000" in production, so link previews on
  // Slack/X/LinkedIn would point at a URL that doesn't exist.
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "https://mediguide-ai-woad.vercel.app"),
  title: "MediGuide — Health Document Intelligence",
  description: DESCRIPTION,
  applicationName: "MediGuide",
  openGraph: {
    title: "MediGuide — Health Document Intelligence",
    description: DESCRIPTION,
    siteName: "MediGuide",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "MediGuide — Health Document Intelligence",
    description: DESCRIPTION,
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${landingSans.variable} ${landingSerif.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
