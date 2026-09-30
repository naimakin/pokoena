import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Figtree, IBM_Plex_Mono } from "next/font/google";
import { ToastProvider } from "@/components/Toast";
import "./globals.css";

// Type v2 (DESIGN.md): one humanist family across display and interface, plus a
// neutral mono for data cells. Replaces the original Barlow Condensed / Outfit /
// Space Mono trio — a compressed industrial grotesque plus a typewriter mono read
// as machinery rather than as a considered instrument, which is the opposite of
// what a tool people sit in front of all day should feel like. Figtree is a
// variable font, so no weight list: the whole 300–900 axis ships in one file.
const figtree = Figtree({ subsets: ["latin"], variable: "--font-figtree" });
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-plex-mono",
});

// Favicon: the POKO mark (components/brand.tsx) pixel-fitted to a 16-grid, inlined
// as a data URI so no public asset (and no middleware matcher change) is needed.
// Literal hex = existing tokens: #2e5aac = --accent, #ffffff = --accent-contrast (light),
// #f7f6f1 / #14161b = --bg light / dark. Keep in sync with globals.css.
const FAVICON_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="3.5" fill="#2e5aac"/>' +
  '<path d="M4 4H8V8H11V9.5" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
  '<circle cx="4" cy="4" r="1.75" fill="#ffffff"/><path d="M11 9.5 13.25 11.75 11 14 8.75 11.75Z" fill="#ffffff"/></svg>';

export const metadata: Metadata = {
  title: "POKO — Project Intelligence & Execution",
  description: "Controlled multi-stakeholder schedule-update workflow for construction programmes.",
  applicationName: "POKO",
  icons: { icon: [{ url: `data:image/svg+xml,${encodeURIComponent(FAVICON_SVG)}`, type: "image/svg+xml" }] },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f6f1" },
    { media: "(prefers-color-scheme: dark)", color: "#14161b" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${figtree.variable} ${plexMono.variable}`}>
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
