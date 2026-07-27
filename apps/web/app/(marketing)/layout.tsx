import type { Metadata } from "next";
import { Geist, Inter, JetBrains_Mono } from "next/font/google";

import "./marketing.css";

/**
 * Marketing shell. Self-hosted via next/font so the three faces the designer specified ship
 * without a render-blocking request to Google — the product's own layout already makes that
 * call for Inter, and a landing page is the one route where first paint is the product.
 */
const geist = Geist({
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  variable: "--font-marketing-display",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-marketing-body",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["500"],
  variable: "--font-marketing-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "TenderCraft AI — Win More Government Tenders with Precision AI",
  description:
    "Automate the bid lifecycle for Indian government tenders: RFP analysis, compliance " +
    "matrices and cited technical writing, with every claim traced to your own documents.",
  openGraph: {
    title: "TenderCraft AI — Win More Government Tenders with Precision AI",
    description:
      "RFP analysis, compliance matrices and cited technical writing for GeM, CPPP and " +
      "state tenders.",
    type: "website",
  },
};

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={`marketing ${geist.variable} ${inter.variable} ${mono.variable}`}>
      {children}
    </div>
  );
}
