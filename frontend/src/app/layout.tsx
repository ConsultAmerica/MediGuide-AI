import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Source_Serif_4 } from "next/font/google";
import "./globals.css";

const landingSans = Plus_Jakarta_Sans({
  variable: "--font-landing-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

const landingSerif = Source_Serif_4({
  variable: "--font-landing-serif",
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  style: ["normal", "italic"],
  // Accent face only: not preloaded, so it never competes with the body
  // font that renders the largest text (LCP). It still swaps in once loaded.
  preload: false,
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
