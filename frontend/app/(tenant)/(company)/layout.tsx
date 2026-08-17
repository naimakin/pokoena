"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import {
  BuildingIcon,
  CalendarIcon,
  ClockIcon,
  CompareIcon,
  DatabaseIcon,
  DiceIcon,
  FlagIcon,
  GanttIcon,
  GridIcon,
  LayersIcon,
  ShieldCheckIcon,
  TrendingUpIcon,
  UploadCloudIcon,
  UsersIcon,
  XIcon,
} from "@/components/icons";

const NAV_GROUPS = [
  {
    label: "Analyze",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: GridIcon, visible: (_user: User | null) => true },
      { href: "/schedule", label: "Schedule", icon: LayersIcon, visible: (_user: User | null) => true },
      { href: "/gantt", label: "Gantt", icon: GanttIcon, visible: (_user: User | null) => true },
      { href: "/evm", label: "EVM / S-Curve", icon: TrendingUpIcon, visible: (_user: User | null) => true },
    ],
  },
  {
    label: "Validate",
    items: [
      { href: "/dcma", label: "DCMA 14-Point", icon: ShieldCheckIcon, visible: (_user: User | null) => true },
      { href: "/risk", label: "Risk Analysis", icon: DiceIcon, visible: (_user: User | null) => true },
      { href: "/logic-diff", label: "Logic Diff", icon: CompareIcon, visible: (_user: User | null) => true },
    ],
  },
  {
    label: "Manage",
    items: [
      { href: "/progress", label: "Progress Input", icon: ClockIcon, visible: (_user: User | null) => true },
      { href: "/completion-plan", label: "Completion Plan", icon: FlagIcon, visible: (_user: User | null) => true },
      { href: "/project-files", label: "Project Files", icon: DatabaseIcon, visible: (_user: User | null) => true },
      {
        href: "/update-period-control",
        label: "Update Period Control",
        icon: CalendarIcon,
        visible: (_user: User | null) => true,
      },
      {
        href: "/export-sync-p6",
        label: "Export / Sync to P6",
        icon: UploadCloudIcon,
        visible: (_user: User | null) => true,
      },
    ],
  },
  {
    label: "Team",
    items: [
      {
        href: "/user-management",
        label: "User Management",
        icon: UsersIcon,
        visible: (user: User | null) =>
          user?.role === "company_admin" ||
          Boolean(user?.project_roles?.includes("user_management")) ||
          Boolean(user?.project_roles?.includes("project_administrator")),
      },
      {
        href: "/review-queue",
        label: "Change Review Queue",
        icon: LayersIcon,
        visible: (user: User | null) => user?.role === "company_admin",
      },
    ],
  },
];

const ROLE_LABEL: Record<string, string> = {
  company_admin: "Company Admin",
  company_employee: "Employee",
};

export default function CompanyLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    api
      .get<User>("/auth/me")
      .then(setUser)
      .catch(() => router.push("/login"));
  }, [router]);

  async function handleSignOut() {
    await api.post("/auth/logout");
    router.push("/login");
    router.refresh();
  }

  const initials = user?.full_name
    ? user.full_name
        .split(" ")
        .map((part) => part[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "";

  return (
    <div className="app-shell">
      <aside className="a-sidebar">
        <div className="brand">
          <div className="mark">
            <BuildingIcon className="icon" />
          </div>
          <div>
            <div className="brand-name">POKO</div>
            <div className="brand-sub">on Primavera P6</div>
          </div>
        </div>

        <nav>
          <div className="nav-group-label">Riverside Logistics Park</div>
          {NAV_GROUPS.map((group) => {
            const items = group.items.filter((item) => item.visible(user));
            if (items.length === 0) return null;
            return (
              <div key={group.label} className="navlist" style={{ marginBottom: ".75rem" }}>
                <div className="nav-group-label">{group.label}</div>
                {items.map(({ href, label, icon: Icon }) => (
                  <Link key={href} href={href} className={`navitem${pathname?.startsWith(href) ? " active" : ""}`}>
                    <Icon className="icon" />
                    <span>{label}</span>
                  </Link>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="a-foot">
          <div className="avatar">{initials}</div>
          <div>
            <div className="who">{user?.full_name ?? "…"}</div>
            <div className="role">{user ? (ROLE_LABEL[user.role] ?? user.role) : ""}</div>
          </div>
          <button className="signout" onClick={handleSignOut} title="Sign out" aria-label="Sign out">
            <XIcon className="icon" />
          </button>
        </div>
      </aside>

      <main className="a-main">{children}</main>
    </div>
  );
}
