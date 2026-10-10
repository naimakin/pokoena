"use client";

// The small info disc beside a page or card title: hover (or focus) shows a short
// explanation of what the block shows; a click pins it open until the close
// button, Escape or a click elsewhere. The popover renders in a portal with
// fixed positioning, so a card's overflow never clips it, and it flips above
// the icon / shifts sideways to stay on screen. Copy lives in lib/help.ts.

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { HelpIcon, XIcon } from "@/components/icons";
import { HELP, type HelpKey } from "@/lib/help";

const WIDTH = 280;
const GAP = 10;
const MARGIN = 12;
const HOVER_DELAY = 180;

interface Place {
  left: number;
  top: number;
  arrow: number;
  above: boolean;
}

export function HelpTip({ id, className }: { id: HelpKey; className?: string }) {
  const entry = HELP[id];
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const timer = useRef<number | null>(null);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [place, setPlace] = useState<Place | null>(null);
  const popId = useId();

  const close = useCallback(() => {
    setOpen(false);
    setPinned(false);
  }, []);

  const measure = useCallback(() => {
    const btn = btnRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const h = popRef.current?.offsetHeight ?? 120;
    const centre = r.left + r.width / 2;
    const left = Math.min(Math.max(centre - WIDTH / 2, MARGIN), window.innerWidth - WIDTH - MARGIN);
    const above = r.bottom + GAP + h > window.innerHeight - MARGIN && r.top - GAP - h > MARGIN;
    setPlace({
      left,
      top: above ? r.top - GAP - h : r.bottom + GAP,
      arrow: Math.min(Math.max(centre - left, 16), WIDTH - 16),
      above,
    });
  }, []);

  useLayoutEffect(() => {
    if (open) measure();
  }, [open, measure]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        close();
        btnRef.current?.focus();
      }
    }
    function onDown(e: MouseEvent) {
      const t = e.target as Node;
      if (!btnRef.current?.contains(t) && !popRef.current?.contains(t)) close();
    }
    // Fixed positioning: follow the icon while the page scrolls or resizes.
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open, close, measure]);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  function hoverIn() {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), HOVER_DELAY);
  }

  function hoverOut() {
    if (timer.current) window.clearTimeout(timer.current);
    if (!pinned) timer.current = window.setTimeout(() => setOpen(false), HOVER_DELAY);
  }

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className={`help-tip no-print${open ? " is-open" : ""}${className ? ` ${className}` : ""}`}
        aria-label={`About: ${entry.title}`}
        aria-expanded={open}
        aria-controls={open ? popId : undefined}
        onClick={(e) => {
          // Inside a fold header or a link-like row: don't toggle that too.
          e.stopPropagation();
          e.preventDefault();
          if (pinned) close();
          else {
            setOpen(true);
            setPinned(true);
          }
        }}
        onMouseEnter={hoverIn}
        onMouseLeave={hoverOut}
        onFocus={() => setOpen(true)}
        onBlur={() => !pinned && setOpen(false)}
      >
        <HelpIcon className="icon" aria-hidden="true" />
      </button>
      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={popRef}
            id={popId}
            role="dialog"
            aria-label={entry.title}
            className={`help-pop${place?.above ? " is-above" : ""}`}
            style={{
              width: WIDTH,
              left: place?.left ?? -9999,
              top: place?.top ?? -9999,
              ["--help-arrow" as string]: `${place?.arrow ?? WIDTH / 2}px`,
            }}
            onMouseEnter={() => timer.current && window.clearTimeout(timer.current)}
            onMouseLeave={hoverOut}
          >
            <div className="help-pop-head">
              <span className="help-pop-title">{entry.title}</span>
              <button type="button" className="help-pop-close" aria-label="Close" onClick={close}>
                <XIcon className="icon icon-sm" aria-hidden="true" />
              </button>
            </div>
            <p className="help-pop-body">{entry.body}</p>
          </div>,
          document.body,
        )}
    </>
  );
}
