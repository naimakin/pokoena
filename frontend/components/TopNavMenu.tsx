"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ComponentType,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
  type SVGProps,
} from "react";
import Link from "next/link";
import { ChevronDownIcon } from "@/components/icons";

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

export interface TopNavMenuItem {
  href: string;
  label: string;
  icon: IconComponent;
}

interface TopNavMenuProps {
  /** Stable key for the section — passed back to onOpenChange and used for element ids. */
  id: string;
  label: string;
  icon: IconComponent;
  items: TopNavMenuItem[];
  /** Current route; the matching item is highlighted and shown under the label. */
  pathname: string | null;
  /** Whether this section owns the current route (keeps the tab's active styling). */
  active: boolean;
  open: boolean;
  /** Some other section's menu is open — hovering this trigger then switches to it. */
  anotherOpen: boolean;
  onOpenChange: (id: string, open: boolean) => void;
  /** Extra marker rendered after the label (e.g. the baseline-gate lock). */
  marker?: ReactNode;
}

type FocusTarget = "first" | "last" | "current";

// Gap between the trigger's bottom edge and the panel, and the minimum
// distance the panel keeps from the viewport's edges.
const PANEL_OFFSET = 4;
const VIEWPORT_MARGIN = 8;

// useLayoutEffect warns during server rendering on React 18. The panel only
// renders on the client after a click, so plain useEffect is an equivalent
// no-op on the server.
const useIsoLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;

function menuItemsOf(panel: HTMLElement | null): HTMLElement[] {
  if (!panel) return [];
  return Array.from(panel.querySelectorAll<HTMLElement>('[role="menuitem"]'));
}

/**
 * A top-bar section rendered as a menu button. The panel is position:fixed and
 * placed from the trigger's bounding rect, so the horizontally scrollable tab
 * strip (overflow-x:auto, which also clips vertically) can't cut it off.
 */
export function TopNavMenu({
  id,
  label,
  icon: Icon,
  items,
  pathname,
  active,
  open,
  anotherOpen,
  onOpenChange,
  marker,
}: TopNavMenuProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef<FocusTarget | null>(null);
  // Set when the menu was opened by sweeping the mouse onto it from another
  // open menu, so the click that usually follows doesn't immediately close it.
  const openedByHover = useRef(false);
  const [pos, setPos] = useState<{ top: number; left: number; maxHeight: number } | null>(null);

  const current = active ? items.find((item) => item.href === pathname) : undefined;
  const triggerId = `topnav-trigger-${id}`;
  const panelId = `topnav-menu-${id}`;

  const focusItem = useCallback((which: FocusTarget) => {
    const list = menuItemsOf(panelRef.current);
    if (list.length === 0) return;
    const target =
      which === "last"
        ? list[list.length - 1]
        : which === "current"
          ? (list.find((el) => el.getAttribute("aria-current") === "page") ?? list[0])
          : list[0];
    target.focus();
  }, []);

  // Place the panel under the trigger, clamped inside the viewport.
  const place = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const panelWidth = panelRef.current?.offsetWidth ?? 0;
    const maxLeft = window.innerWidth - panelWidth - VIEWPORT_MARGIN;
    const left = Math.max(VIEWPORT_MARGIN, Math.min(rect.left, maxLeft));
    const top = rect.bottom + PANEL_OFFSET;
    const maxHeight = Math.max(160, window.innerHeight - top - VIEWPORT_MARGIN);
    setPos((prev) =>
      prev && prev.top === top && prev.left === left && prev.maxHeight === maxHeight ? prev : { top, left, maxHeight }
    );
  }, []);

  useIsoLayoutEffect(() => {
    if (!open) {
      openedByHover.current = false;
      setPos(null);
      return;
    }
    place();
    // The trigger moves when the tab strip scrolls sideways or the window resizes.
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, place]);

  // Once the panel is positioned, move focus into it if it was opened from the keyboard.
  const positioned = pos !== null;
  useEffect(() => {
    if (!open || !positioned || !pendingFocus.current) return;
    const which = pendingFocus.current;
    pendingFocus.current = null;
    focusItem(which);
  }, [open, positioned, focusItem]);

  // Close on outside pointer-down and on Escape while open.
  useEffect(() => {
    if (!open) return;
    function handlePointerDown(e: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) onOpenChange(id, false);
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.preventDefault();
      onOpenChange(id, false);
      triggerRef.current?.focus();
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, id, onOpenChange]);

  function handleTriggerClick(e: ReactMouseEvent<HTMLButtonElement>) {
    // detail === 0 means the click came from the keyboard (Enter / Space):
    // follow the menu-button pattern and move focus onto an item.
    if (!open && e.detail === 0) pendingFocus.current = "current";
    if (open && openedByHover.current) {
      openedByHover.current = false;
      return;
    }
    onOpenChange(id, !open);
  }

  function handleTriggerKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const which: FocusTarget = e.key === "ArrowDown" ? "first" : "last";
    if (open) {
      focusItem(which);
    } else {
      pendingFocus.current = which;
      onOpenChange(id, true);
    }
  }

  function handlePanelKeyDown(e: ReactKeyboardEvent<HTMLDivElement>) {
    const list = menuItemsOf(panelRef.current);
    if (list.length === 0) return;
    const index = list.indexOf(document.activeElement as HTMLElement);
    let next: number | null = null;
    if (e.key === "ArrowDown") next = index < 0 ? 0 : (index + 1) % list.length;
    else if (e.key === "ArrowUp") next = index < 0 ? list.length - 1 : (index - 1 + list.length) % list.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = list.length - 1;
    else if (e.key === "Tab") {
      // Hand focus back to the trigger without preventing the default, so Tab /
      // Shift+Tab then carries on from there, and close the panel.
      triggerRef.current?.focus();
      onOpenChange(id, false);
      return;
    }
    if (next !== null) {
      e.preventDefault();
      list[next].focus();
    }
  }

  const panelStyle: CSSProperties = pos
    ? { top: pos.top, left: pos.left, maxHeight: pos.maxHeight }
    : { top: 0, left: 0, visibility: "hidden" };

  return (
    <div className="topnav-menu" ref={rootRef}>
      <button
        ref={triggerRef}
        id={triggerId}
        type="button"
        className={`topnav-tab topnav-trigger${active ? " active" : ""}${open ? " open" : ""}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-label={current ? `${label}, current page: ${current.label}` : label}
        title={current ? `${label} · ${current.label}` : label}
        onClick={handleTriggerClick}
        onKeyDown={handleTriggerKeyDown}
        onPointerEnter={(e) => {
          // Menubar convention: once one section's menu is open, sweeping the
          // mouse across the other sections switches between them. Mouse only
          // — a touch tap also fires pointerenter and would fight the click toggle.
          if (e.pointerType === "mouse" && anotherOpen && !open) {
            openedByHover.current = true;
            onOpenChange(id, true);
          }
        }}
        onPointerLeave={() => {
          openedByHover.current = false;
        }}
      >
        <Icon className="icon topnav-tab-icon" />
        <span className={`topnav-tab-text${current ? " has-current" : ""}`}>
          <span className="topnav-tab-label">{label}</span>
          {current && <span className="topnav-tab-current">{current.label}</span>}
        </span>
        {marker}
        <ChevronDownIcon className="icon topnav-caret" aria-hidden="true" />
      </button>

      {open && (
        <div
          ref={panelRef}
          id={panelId}
          role="menu"
          aria-labelledby={triggerId}
          className="topnav-panel"
          style={panelStyle}
          onKeyDown={handlePanelKeyDown}
        >
          {items.map(({ href, label: itemLabel, icon: ItemIcon }) => {
            const isCurrent = pathname === href;
            return (
              <Link
                key={`${href}-${itemLabel}`}
                href={href}
                role="menuitem"
                tabIndex={-1}
                aria-current={isCurrent ? "page" : undefined}
                className={`topnav-panel-item${isCurrent ? " active" : ""}`}
                onClick={() => onOpenChange(id, false)}
              >
                <ItemIcon className="icon" />
                <span>{itemLabel}</span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
