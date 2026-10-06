"use client";

import { useEffect, useId, useRef, useState, type ComponentType, type SVGProps } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { User } from "@/lib/types";
import { CheckIcon, ChevronDownIcon, HomeIcon, LogOutIcon, SettingsIcon } from "@/components/icons";
import { getLandingPage, setLandingPage } from "@/lib/landing";

export interface UserMenuLink {
  href: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

/** The account menu in the header's top-right corner (AppDynamics-style):
 *  who you are, your profile, the admin pages you're allowed to open, sign out.
 *  Account and administration pages live here rather than in the sidebar,
 *  which is kept for working on the selected project. */
export function UserMenu({
  user,
  roleLabel,
  adminLinks,
  onSignOut,
}: {
  user: User | null;
  roleLabel: string;
  adminLinks: UserMenuLink[];
  onSignOut: () => void;
}) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const [landing, setLanding] = useState<string | null>(null);

  useEffect(() => {
    if (open) setLanding(getLandingPage());
  }, [open]);

  function chooseLanding(path: string | null) {
    setLandingPage(path);
    setLanding(path);
  }

  const isLanding = (landing ?? "/dashboard") === pathname;

  const initials = user?.full_name
    ? user.full_name
        .split(" ")
        .map((part) => part[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "";

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="user-menu" ref={wrapRef}>
      <button
        ref={buttonRef}
        type="button"
        className="user-menu-button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`Account menu for ${user?.full_name ?? "you"}`}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="avatar">{initials}</span>
        <span className="user-menu-who">
          <span className="who">{user?.full_name ?? "…"}</span>
          <span className="role">{roleLabel}</span>
        </span>
        <ChevronDownIcon className="icon user-menu-caret" aria-hidden="true" />
      </button>

      {open && (
        <div className="user-menu-panel" id={panelId}>
          <div className="user-menu-head">
            <span className="avatar is-lg">{initials}</span>
            <span className="user-menu-id">
              <span className="user-menu-name">{user?.full_name}</span>
              <span className="user-menu-email">{user?.email}</span>
              <span className="user-menu-role">{roleLabel}</span>
            </span>
          </div>

          <nav className="user-menu-group" aria-label="Account">
            <Link className="user-menu-link" href="/administration/profile">
              <SettingsIcon className="icon" /> My profile
            </Link>
            {isLanding ? (
              <span className="user-menu-link is-static">
                <CheckIcon className="icon" /> This page opens after sign-in
              </span>
            ) : (
              <button type="button" className="user-menu-link" onClick={() => chooseLanding(pathname)}>
                <HomeIcon className="icon" /> Set this page as my landing page
              </button>
            )}
            {landing && landing !== "/dashboard" && (
              <button type="button" className="user-menu-link is-quiet" onClick={() => chooseLanding(null)}>
                Reset landing page to Dashboard
              </button>
            )}
          </nav>

          {adminLinks.length > 0 && (
            <nav className="user-menu-group" aria-label="Administration">
              <div className="user-menu-label">Administration</div>
              {adminLinks.map((l) => (
                <Link
                  key={l.href}
                  className={`user-menu-link${pathname === l.href ? " is-active" : ""}`}
                  href={l.href}
                  aria-current={pathname === l.href ? "page" : undefined}
                >
                  <l.icon className="icon" /> {l.label}
                </Link>
              ))}
            </nav>
          )}

          <div className="user-menu-foot">
            <button type="button" className="btn btn-secondary btn-sm" onClick={onSignOut}>
              <LogOutIcon className="icon" /> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

