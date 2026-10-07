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
  type ReactNode,
  type RefObject,
  type SVGProps,
} from "react";
import Link from "next/link";
import { ChevronDownIcon } from "@/components/icons";

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

export interface SideNavItem {
  href: string;
  label: string;
  /** A count shown after the label (e.g. unread mentions on My Desk). */
  badge?: number;
}

export interface SideNavSection {
  key: string;
  label: string;
  icon: IconComponent;
  href: string;
  /** Pages under this section, already filtered for the viewer. Empty → the section is a plain link. */
  items: SideNavItem[];
  /** Extra marker rendered after the label (e.g. the baseline-gate lock). */
  marker?: ReactNode;
}

interface SideNavProps {
  id: string;
  sections: SideNavSection[];
  /** Key of the section that owns the current route (null when none does). */
  activeKey: string | null;
  pathname: string | null;
  /** Desktop collapsed state: a 56px icon rail whose sections open a flyout. */
  rail: boolean;
  /** Called when a link is followed — the layout closes the mobile drawer. */
  onNavigate: () => void;
}

// Gap between the rail and its flyout, and the minimum distance the flyout
// keeps from the viewport's edges.
const FLYOUT_OFFSET = 6;
const VIEWPORT_MARGIN = 8;

// useLayoutEffect warns during server rendering on React 18. The flyout only
// renders on the client after a click, so plain useEffect is an equivalent
// no-op on the server.
const useIsoLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;

function linksOf(panel: HTMLElement | null): HTMLElement[] {
  if (!panel) return [];
  return Array.from(panel.querySelectorAll<HTMLElement>("a[href]"));
}

/**
 * The company shell's left navigation. Expanded, every section is an
 * accordion row (several may be open at once; the one holding the current
 * page opens by itself). In the collapsed rail a section's icon opens a
 * flyout to the right instead. The mobile drawer is the expanded form.
 */
export function SideNav({ id, sections, activeKey, pathname, rail, onNavigate }: SideNavProps) {
  const [openKeys, setOpenKeys] = useState<string[]>(() => (activeKey ? [activeKey] : []));
  const [flyoutKey, setFlyoutKey] = useState<string | null>(null);

  // Open the section that holds the current page — on arrival and on every
  // navigation — without closing anything the viewer opened themselves.
  useEffect(() => {
    if (!activeKey) return;
    setOpenKeys((prev) => (prev.includes(activeKey) ? prev : [...prev, activeKey]));
  }, [activeKey, pathname]);

  // A flyout never outlives a route change or the rail itself.
  useEffect(() => {
    setFlyoutKey(null);
  }, [pathname, rail]);

  const toggleOpen = useCallback((key: string) => {
    setOpenKeys((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  }, []);

  const closeFlyout = useCallback(() => setFlyoutKey(null), []);

  return (
    <aside id={id} className="a-sidenav" aria-label="Main navigation">
      <nav aria-label="Main">
        <ul className="sidenav-list">
          {sections.map((section) =>
            section.items.length === 0 ? (
              <li key={section.key}>
                <TopLink section={section} pathname={pathname} rail={rail} onNavigate={onNavigate} />
              </li>
            ) : (
              <SectionRow
                key={section.key}
                section={section}
                pathname={pathname}
                current={section.key === activeKey}
                rail={rail}
                open={openKeys.includes(section.key)}
                flyoutOpen={rail && flyoutKey === section.key}
                onToggle={() => {
                  if (rail) setFlyoutKey((prev) => (prev === section.key ? null : section.key));
                  else toggleOpen(section.key);
                }}
                onCloseFlyout={closeFlyout}
                onNavigate={onNavigate}
              />
            )
          )}
        </ul>
      </nav>
    </aside>
  );
}

function TopLink({
  section,
  pathname,
  rail,
  onNavigate,
}: {
  section: SideNavSection;
  pathname: string | null;
  rail: boolean;
  onNavigate: () => void;
}) {
  const Icon = section.icon;
  const active = pathname === section.href;
  return (
    <Link
      href={section.href}
      className={`sidenav-row${active ? " is-active" : ""}`}
      aria-current={active ? "page" : undefined}
      aria-label={section.label}
      title={rail ? section.label : undefined}
      onClick={onNavigate}
    >
      <Icon className="icon sidenav-icon" />
      <span className="sidenav-label">{section.label}</span>
      {section.marker && <span className="sidenav-marker">{section.marker}</span>}
    </Link>
  );
}

function SectionRow({
  section,
  pathname,
  current,
  rail,
  open,
  flyoutOpen,
  onToggle,
  onCloseFlyout,
  onNavigate,
}: {
  section: SideNavSection;
  pathname: string | null;
  current: boolean;
  rail: boolean;
  open: boolean;
  flyoutOpen: boolean;
  onToggle: () => void;
  onCloseFlyout: () => void;
  onNavigate: () => void;
}) {
  const rootRef = useRef<HTMLLIElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const Icon = section.icon;
  const listId = `sidenav-list-${section.key}`;
  const flyoutId = `sidenav-flyout-${section.key}`;
  const currentItem = current ? section.items.find((item) => item.href === pathname) : undefined;

  // Close the flyout on outside pointer-down and on Escape (focus returns to the icon).
  useEffect(() => {
    if (!flyoutOpen) return;
    function handlePointerDown(e: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) onCloseFlyout();
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.preventDefault();
      onCloseFlyout();
      triggerRef.current?.focus();
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [flyoutOpen, onCloseFlyout]);

  const expanded = rail ? flyoutOpen : open;
  const label = currentItem ? `${section.label}, current page: ${currentItem.label}` : section.label;

  return (
    <li ref={rootRef} className={`sidenav-section${open && !rail ? " is-open" : ""}`}>
      <button
        ref={triggerRef}
        type="button"
        className={`sidenav-row${current ? " is-current" : ""}${flyoutOpen ? " is-flyout" : ""}`}
        aria-expanded={expanded}
        aria-controls={expanded ? (rail ? flyoutId : listId) : undefined}
        aria-label={label}
        title={rail ? section.label : undefined}
        onClick={onToggle}
        onKeyDown={(e) => {
          // Rail: ArrowDown opens the flyout the way it opens a menu button.
          if (rail && !flyoutOpen && e.key === "ArrowDown") {
            e.preventDefault();
            onToggle();
          }
        }}
      >
        <Icon className="icon sidenav-icon" />
        <span className="sidenav-label">{section.label}</span>
        {section.marker && <span className="sidenav-marker">{section.marker}</span>}
        <ChevronDownIcon className="icon sidenav-chevron" aria-hidden="true" />
      </button>

      {!rail && open && (
        <ul id={listId} className="sidenav-children">
          {section.items.map((item) => (
            <li key={`${item.href}-${item.label}`}>
              <ChildLink item={item} pathname={pathname} onNavigate={onNavigate} />
            </li>
          ))}
        </ul>
      )}

      {flyoutOpen && (
        <RailFlyout
          id={flyoutId}
          section={section}
          pathname={pathname}
          triggerRef={triggerRef}
          onClose={onCloseFlyout}
          onNavigate={() => {
            onCloseFlyout();
            onNavigate();
          }}
        />
      )}
    </li>
  );
}

function ChildLink({
  item,
  pathname,
  onNavigate,
}: {
  item: SideNavItem;
  pathname: string | null;
  onNavigate: () => void;
}) {
  const active = pathname === item.href;
  return (
    <Link
      href={item.href}
      className={`sidenav-child${active ? " is-active" : ""}`}
      aria-current={active ? "page" : undefined}
      onClick={onNavigate}
    >
      <span>{item.label}</span>
      {item.badge ? (
        <span className="sidenav-badge" aria-label={`${item.badge} new`}>
          {item.badge > 99 ? "99+" : item.badge}
        </span>
      ) : null}
    </Link>
  );
}

function RailFlyout({
  id,
  section,
  pathname,
  triggerRef,
  onClose,
  onNavigate,
}: {
  id: string;
  section: SideNavSection;
  pathname: string | null;
  triggerRef: RefObject<HTMLButtonElement>;
  onClose: () => void;
  onNavigate: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number; maxHeight: number } | null>(null);

  // Beside the rail icon, top-aligned with it, clamped inside the viewport.
  const place = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const height = panelRef.current?.offsetHeight ?? 0;
    const left = rect.right + FLYOUT_OFFSET;
    const top = Math.max(VIEWPORT_MARGIN, Math.min(rect.top, window.innerHeight - height - VIEWPORT_MARGIN));
    const maxHeight = Math.max(160, window.innerHeight - top - VIEWPORT_MARGIN);
    setPos((prev) =>
      prev && prev.top === top && prev.left === left && prev.maxHeight === maxHeight ? prev : { top, left, maxHeight }
    );
  }, [triggerRef]);

  useIsoLayoutEffect(() => {
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [place]);

  // Once placed, move focus onto the current page (or the first one).
  const positioned = pos !== null;
  useEffect(() => {
    if (!positioned) return;
    const list = linksOf(panelRef.current);
    (list.find((el) => el.getAttribute("aria-current") === "page") ?? list[0])?.focus();
  }, [positioned]);

  function handleKeyDown(e: ReactKeyboardEvent<HTMLDivElement>) {
    const list = linksOf(panelRef.current);
    if (list.length === 0) return;
    const index = list.indexOf(document.activeElement as HTMLElement);
    let next: number | null = null;
    if (e.key === "ArrowDown") next = index < 0 ? 0 : (index + 1) % list.length;
    else if (e.key === "ArrowUp") next = index < 0 ? list.length - 1 : (index - 1 + list.length) % list.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = list.length - 1;
    else if (e.key === "Tab") {
      // Hand focus back to the rail icon without preventing the default, so
      // Tab / Shift+Tab carries on from there, and close the flyout.
      triggerRef.current?.focus();
      onClose();
      return;
    }
    if (next !== null) {
      e.preventDefault();
      list[next].focus();
    }
  }

  const style: CSSProperties = pos
    ? { top: pos.top, left: pos.left, maxHeight: pos.maxHeight }
    : { top: 0, left: 0, visibility: "hidden" };

  return (
    <div
      ref={panelRef}
      id={id}
      className="sidenav-flyout"
      role="group"
      aria-label={section.label}
      style={style}
      onKeyDown={handleKeyDown}
    >
      <div className="sidenav-flyout-title" aria-hidden="true">
        {section.label}
      </div>
      <ul className="sidenav-flyout-list">
        {section.items.map((item) => (
          <li key={`${item.href}-${item.label}`}>
            <ChildLink item={item} pathname={pathname} onNavigate={onNavigate} />
          </li>
        ))}
      </ul>
    </div>
  );
}
