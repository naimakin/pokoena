import type { Metadata } from "next";
import type { ReactNode } from "react";
import { ToastProvider } from "@/components/Toast";
import "./globals.css";

export const metadata: Metadata = {
  title: "POKO — Project Intelligence & Execution",
  description: "Controlled multi-stakeholder schedule-update workflow on top of Primavera P6.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
