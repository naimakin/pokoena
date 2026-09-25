"use client";

import { useEffect, useState, type ComponentType, type ReactNode, type SVGProps } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import { ProjectProvider, useProjectContext } from "@/lib/project-context";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { BaselineGate, BASELINE_GATED_SECTIONS } from "@/components/BaselineGate";
import {
  AlertTriangleIcon,
  BarChartIcon,
  BuildingIcon,
  CalendarIcon,
  ClockIcon,
  CompareIcon,
  DatabaseIcon,
  DiceIcon,
  DownloadIcon,
  FlagIcon,
  FolderIcon,
  GanttIcon,
  GridIcon,
  LayersIcon,
  LockIcon,
  SettingsIcon,
  ShieldCheckIcon,
  SparkleIcon,
  TrendingUpIcon,
  UsersIcon,
  XIcon,
} from "@/components/icons";

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;
type Visible = (user: User | null) => boolean;

interface NavChild {
  href: string;
  label: string;
  icon: IconComponent;
  visible: Visible;
}

interface NavSection {
  key: string;
  label: string;
  icon: IconComponent;
  href: string;
  visible: Visible;
  children: NavChild[];
}

const always: Visible = () => true;

const canManageTeam: Visible = (user) =>
  user?.role === "company_admin" ||
  Boolean(user?.project_roles?.includes("user_management")) ||
  Boolean(user?.project_roles?.includes("project_administrator"));

const isCompanyAdmin: Visible = (user) => user?.role === "company_admin";

// Where a destination is reused under more than one top section, TOP_SECTIONS
// order below decides which section is treated as "active" when that route is
// open (first match wins).
const TOP_SECTIONS: NavSection[] = [
  { key: "dashboard", label: "Dashboard", icon: GridIcon, href: "/dashboard", visible: always, children: [] },
  {
    key: "portfolio",
    label: "Portfolio",
    icon: BuildingIcon,
    href: "/projects",
    visible: always,
    children: [
      { href: "/projects", label: "Projects", icon: FolderIcon, visible: canManageTeam },
      { href: "/portfolio/dashboard", label: "Portfolio Dashboard", icon: GridIcon, visible: always },
      { href: "/project-files", label: "Program Library", icon: DatabaseIcon, visible: always },
    ],
  },
  {
    key: "planning",
    label: "Planning",
    icon: CalendarIcon,
    href: "/planning/wbs",
    visible: always,
    children: [
      { href: "/planning/baselines", label: "Baselines", icon: LockIcon, visible: always },
      { href: "/planning/wbs", label: "WBS", icon: LayersIcon, visible: always },
      { href: "/gantt", label: "Schedule", icon: GanttIcon, visible: always },
      { href: "/planning/float-path", label: "Float Path", icon: TrendingUpIcon, visible: always },
      { href: "/planning/milestones", label: "Milestones", icon: FlagIcon, visible: always },
      { href: "/planning/ai-schedule-builder", label: "AI Schedule Builder", icon: SparkleIcon, visible: always },
      { href: "/export-sync-p6", label: "Export / Sync to P6", icon: DownloadIcon, visible: always },
    ],
  },
  {
    key: "execution",
    label: "Execution",
    icon: FlagIcon,
    href: "/execution/my-focus",
    visible: always,
    children: [
      { href: "/execution/my-focus", label: "My Focus", icon: FlagIcon, visible: always },
      { href: "/execution/project-status", label: "Project Status", icon: GridIcon, visible: always },
      { href: "/progress", label: "Project Activities", icon: ClockIcon, visible: always },
      { href: "/recovery-plan", label: "Recovery Plan", icon: TrendingUpIcon, visible: always },
      { href: "/execution/changes", label: "Changes", icon: CompareIcon, visible: always },
      { href: "/update-period-control", label: "Update Period Control", icon: CalendarIcon, visible: always },
      { href: "/execution/lookahead", label: "Lookahead", icon: CalendarIcon, visible: always },
      { href: "/execution/issues", label: "Issues", icon: AlertTriangleIcon, visible: always },
      { href: "/review-queue", label: "Flag Reviews", icon: CompareIcon, visible: isCompanyAdmin },
    ],
  },
  {
    key: "risk",
    label: "Risk",
    icon: AlertTriangleIcon,
    href: "/risk",
    visible: always,
    children: [
      { href: "/risk", label: "Risk Dashboard", icon: DiceIcon, visible: always },
      { href: "/risk/register", label: "Risk Register", icon: LayersIcon, visible: always },
      { href: "/risk/matrix", label: "Risk Matrix", icon: GridIcon, visible: always },
      { href: "/risk/mitigation-plans", label: "Mitigation Plans", icon: ShieldCheckIcon, visible: always },
    ],
  },
  {
    key: "reporting",
    label: "Reporting",
    icon: BarChartIcon,
    href: "/reporting/reports",
    visible: always,
    // Progress Reports / Schedule Reports / Custom Reports / Project Dashboard
    // were four empty slots for the same thing: a report you assemble and hand
    // to someone. They are one page now, and the old routes redirect to it.
    children: [
      { href: "/reporting/reports", label: "Reports", icon: BarChartIcon, visible: always },
      { href: "/evm", label: "S-Curve & EVM", icon: TrendingUpIcon, visible: always },
      { href: "/dcma", label: "DCMA 14-Point", icon: ShieldCheckIcon, visible: always },
      { href: "/logic-diff", label: "Logic Diff", icon: CompareIcon, visible: always },
    ],
  },
  {
    key: "ai",
    label: "AI",
    icon: SparkleIcon,
    href: "/ai/assistant",
    visible: always,
    children: [
      { href: "/ai/assistant", label: "AI Assistant", icon: SparkleIcon, visible: always },
      { href: "/ai/schedule-generator", label: "Schedule Generator", icon: GanttIcon, visible: always },
      { href: "/ai/progress-analysis", label: "Progress Analysis", icon: TrendingUpIcon, visible: always },
      { href: "/ai/delay-analysis", label: "Delay Analysis", icon: ClockIcon, visible: always },
      { href: "/ai/risk-analysis", label: "Risk Analysis", icon: DiceIcon, visible: always },
      { href: "/ai/insights", label: "AI Insights", icon: SparkleIcon, visible: always },
    ],
  },
  {
    key: "administration",
    label: "Administration",
    icon: SettingsIcon,
    href: "/user-management",
    visible: canManageTeam,
    children: [
      { href: "/user-management", label: "Users", icon: UsersIcon, visible: canManageTeam },
      { href: "/administration/profile", label: "My Profile", icon: UsersIcon, visible: always },
      { href: "/administration/roles", label: "Roles", icon: ShieldCheckIcon, visible: canManageTeam },
      { href: "/administration/contractors", label: "Contractors", icon: BuildingIcon, visible: canManageTeam },
      { href: "/administration/teams", label: "Teams", icon: UsersIcon, visible: canManageTeam },
      { href: "/administration/settings", label: "Settings", icon: SettingsIcon, visible: canManageTeam },
    ],
  },
];

const ROLE_LABEL: Record<string, string> = {
  company_admin: "Company Admin",
  company_employee: "Employee",
};

// Exact match, not a prefix check: several sibling routes share a prefix
// (e.g. /risk and /risk/register), and every destination here is a static
// leaf route, so there's no nested-segment case that would need startsWith.
function isActiveHref(pathname: string | null, href: string): boolean {
  return pathname === href;
}

// Small lock marker on gated top-nav tabs while the selected project has no
// baseline. Rendered inside <ProjectProvider>, so it can read the context.
function GatedTabLock() {
  const { project, baselineReady } = useProjectContext();
  if (!project || baselineReady !== false) return null;
  return <LockIcon className="icon" style={{ width: 12, height: 12, opacity: 0.7 }} />;
}

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

  const visibleSections = TOP_SECTIONS.filter((section) => {
    if (!section.visible(user)) return false;
    if (section.children.length === 0) return true;
    return section.children.some((child) => child.visible(user));
  });

  const activeSection =
    visibleSections.find((section) =>
      section.children.length > 0
        ? section.children.some((child) => child.visible(user) && isActiveHref(pathname, child.href))
        : isActiveHref(pathname, section.href)
    ) ?? null;

  const sidebarItems = activeSection?.children.filter((child) => child.visible(user)) ?? [];

  return (
    <ProjectProvider>
      <div className="tenant-shell">
        <div className="a-topnav">
          <div className="brand">
            <div className="mark">
              <BuildingIcon className="icon" />
            </div>
            <div>
              <div className="brand-name">POKO</div>
            </div>
          </div>

          <nav className="a-topnav-tabs">
            {visibleSections.map((section) => {
              const active = section.key === activeSection?.key;
              const Icon = section.icon;
              return (
                <Link
                  key={section.key}
                  href={section.href}
                  className={`topnav-tab${active ? " active" : ""}`}
                >
                  <Icon className="icon" />
                  <span>{section.label}</span>
                  {BASELINE_GATED_SECTIONS.has(section.key) && <GatedTabLock />}
                </Link>
              );
            })}
          </nav>

          <div className="a-topnav-right">
            <ProjectSwitcher />
            <div className="topnav-user">
              <div className="avatar">{initials}</div>
              <div>
                <div className="who">{user?.full_name ?? "…"}</div>
                <div className="role">{user ? (ROLE_LABEL[user.role] ?? user.role) : ""}</div>
              </div>
              <button className="signout" onClick={handleSignOut} title="Sign out" aria-label="Sign out">
                <XIcon className="icon" />
              </button>
            </div>
          </div>
        </div>

        <div className="tenant-body">
          {sidebarItems.length > 0 && (
            <aside className="a-sidebar">
              <nav className="navlist">
                {sidebarItems.map(({ href, label, icon: Icon }) => (
                  <Link
                    key={`${activeSection?.key}-${href}-${label}`}
                    href={href}
                    className={`navitem${isActiveHref(pathname, href) ? " active" : ""}`}
                  >
                    <Icon className="icon" />
                    <span>{label}</span>
                  </Link>
                ))}
              </nav>
            </aside>
          )}

          <main className="a-main">
            <BaselineGate gated={BASELINE_GATED_SECTIONS.has(activeSection?.key ?? "")}>{children}</BaselineGate>
          </main>
        </div>
      </div>
    </ProjectProvider>
  );
}
