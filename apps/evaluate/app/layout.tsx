import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import tokens from "../../../design/tokens.json";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-body-fallback", display: "swap" });

export const metadata: Metadata = {
  title: "TenderCraft Evaluate",
  description: "Defensible, audit-ready tender evaluation for public authorities.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: tokens.color["surface-alt"],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}
