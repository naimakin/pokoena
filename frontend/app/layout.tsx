import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Barlow_Condensed, Outfit, Space_Mono } from "next/font/google";
import { ToastProvider } from "@/components/Toast";
import "./globals.css";

// Fonts from the reference Poko design system: Barlow Condensed for display
// headings, Outfit for body copy (Aptos, DESIGN.md's stated preference,
// isn't an open/Google font), Space Mono for tabular/data cells.
const barlowCondensed = Barlow_Condensed({
  subsets: ["latin"],
  weight: ["600", "700"],
  variable: "--font-barlow",
});
const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" });
const spaceMono = Space_Mono({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-space-mono" });

export const metadata: Metadata = {
  title: "POKO — Project Intelligence & Execution",
  description: "Controlled multi-stakeholder schedule-update workflow on top of Primavera P6.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${barlowCondensed.variable} ${outfit.variable} ${spaceMono.variable}`}>
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
