import type { Metadata } from "next";
import { SiteHome } from "./site/SiteHome";

export const metadata: Metadata = {
  title: "MediGuide — Your health information. Finally connected.",
  description:
    "Turn medical reports into verified, understandable information with connected timelines, grounded explanations and direct links to original evidence.",
};

export default function HomePage() {
  return <SiteHome />;
}
