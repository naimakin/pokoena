import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Roboto } from "next/font/google";
import { ToastProvider } from "@/components/Toast";
import "./globals.css";

// Type v3 (DESIGN.md): Roboto across display, interface and data (tabular
// figures — the owner dropped the monospace data face as too machine-like).
// Roboto replaced Figtree when the owner moved POKO to an
// AppDynamics-inspired "indigo chrome" direction — a neutral, engineered
// grotesque that sits quietly under a coloured header instead of competing
// with it. Roboto on Google Fonts is static here, so the weights are listed:
// 400 body, 500 labels/titles (DESIGN.md: Medium is the label weight — there
// is no 600), 700 emphasis inside dense data, 300 for the odd large numeral.
const roboto = Roboto({
  subsets: ["latin"],
  weight: ["300", "400", "500", "700"],
  variable: "--font-roboto",
});

// Favicon: the POKO mark (components/brand.tsx) pixel-fitted to a 16-grid, inlined
// as a data URI so no public asset (and no middleware matcher change) is needed.
// Literal hex = existing tokens: #5b45d6 = --accent, #ffffff = --accent-contrast (light),
// #1e1650 = --chrome-bg-1 (light; the header bar's colour). Keep in sync with globals.css.
const FAVICON_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="3.5" fill="#5b45d6"/>' +
  '<path d="M4 4H8V8H11V9.5" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
  '<circle cx="4" cy="4" r="1.75" fill="#ffffff"/><path d="M11 9.5 13.25 11.75 11 14 8.75 11.75Z" fill="#ffffff"/></svg>';

export const metadata: Metadata = {
  title: "POKO — Project Intelligence & Execution",
  description: "Controlled multi-stakeholder schedule-update workflow for construction programmes.",
  applicationName: "POKO",
  icons: { icon: [{ url: `data:image/svg+xml,${encodeURIComponent(FAVICON_SVG)}`, type: "image/svg+xml" }] },
};

// The browser's own chrome matches the header bar (--chrome-bg-1, light / dark).
export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#1e1650" },
    { media: "(prefers-color-scheme: dark)", color: "#120d33" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  // suppressHydrationWarning: the company shell's inline script may set
  // data-sidebar on <html> before hydration (the remembered collapsed rail).
  return (
    <html lang="en" className={roboto.variable} suppressHydrationWarning>
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
