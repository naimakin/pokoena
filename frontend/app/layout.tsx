import type { Metadata } from "next";
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

export const metadata: Metadata = {
  title: "POKO — Project Intelligence & Execution",
  description: "Controlled multi-stakeholder schedule-update workflow for construction programmes.",
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
