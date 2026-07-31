import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import { getLocale } from "@/lib/locale";

import tokens from "../../../design/tokens.json";

import "./globals.css";

// San Francisco is served by the OS on Apple hardware (see --font-body in globals.css), so
// Inter is the CROSS-PLATFORM FALLBACK rather than the primary face — hence the variable
// name. Lexend went with the iOS restyle: Apple's language uses one family at every size,
// and it is one less font to fetch.
const inter = Inter({ subsets: ["latin"], variable: "--font-body-fallback", display: "swap" });

export const metadata: Metadata = {
  title: "TenderCraft",
  description: "From tender PDF to evaluator-ready proposal. Cited, compliant, human-approved.",
};

// themeColor tints the browser/OS chrome to match the app background — part of why an
// installed web app reads as native rather than as a page. Read from the token rather than
// written as a hex: Next metadata cannot take a CSS var, so this is the only way it stays
// in step with the palette.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: tokens.color["surface-alt"],
};

// `lang` is not decoration: a screen reader picks its voice from it, so French copy under
// lang="en" is read aloud with English phonemes. Async because the locale is a cookie/profile
// read — this layout has no other data dependency, so it costs nothing on the critical path.
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  return (
    <html lang={locale} className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}
