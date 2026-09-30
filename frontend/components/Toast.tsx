"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";
import { AlertTriangleIcon, CheckIcon, XIcon } from "@/components/icons";

type ToastTone = "success" | "error";

interface ToastContextValue {
  showToast: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<{ message: string; tone: ToastTone } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((next: string, tone: ToastTone = "success") => {
    setToast({ message: next, tone });
    if (timerRef.current) clearTimeout(timerRef.current);
    // Errors stay until dismissed; success toasts fade on their own.
    timerRef.current = tone === "error" ? null : setTimeout(() => setToast(null), 3200);
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {toast && (
        <div
          className={`toast${toast.tone === "error" ? " is-error" : ""}`}
          role={toast.tone === "error" ? "alert" : "status"}
        >
          {toast.tone === "error" ? <AlertTriangleIcon className="icon" /> : <CheckIcon className="icon" />}
          <span>{toast.message}</span>
          {toast.tone === "error" && (
            <button type="button" className="toast-close" onClick={() => setToast(null)} aria-label="Dismiss">
              <XIcon className="icon icon-sm" />
            </button>
          )}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}
