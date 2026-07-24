import type { Metadata } from "next";
import { Inter, Lexend } from "next/font/google";

import "./globals.css";

const lexend = Lexend({ subsets: ["latin"], variable: "--font-heading", display: "swap" });
const inter = Inter({ subsets: ["latin"], variable: "--font-body", display: "swap" });

export const metadata: Metadata = {
  title: "TenderCraft",
  description: "From tender PDF to evaluator-ready proposal. Cited, compliant, human-approved.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${lexend.variable} ${inter.variable}`}>
      <body>{children}</body>
    </html>
  );
}
