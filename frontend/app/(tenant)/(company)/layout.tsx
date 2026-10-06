"use client";

import { useCallback, useEffect, useRef, useState, type ComponentType, type ReactNode, type SVGProps } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import { ProjectProvider, useProjectContext } from "@/lib/project-context";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { BaselineGate, BASELINE_GATED_SECTIONS, isBaselineGated } from "@/components/BaselineGate";
import { SideNav, type SideNavSection } from "@/components/SideNav";
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
  LogOutIcon,
  MenuIcon,
  PinIcon,
  SettingsIcon,
  ShieldCheckIcon,
  SimulationIcon,
  TrendingUpIcon,
  UsersIcon,
} from "@/components/icons";
import { PokoGlyph } from "@/components/brand";

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
    label: "Projects",
    icon: BuildingIcon,
    href: "/projects",
    visible: always,
    children: [
      { href: "/projects", label: "Projects", icon: FolderIcon, visible: canManageTeam },
      { href: "/portfolio/dashboard", label: "Portfolio Dashboard", icon: GridIcon, visible: always },
    ],
  },
  {
    key: "planning",
    label: "Programme",
    icon: CalendarIcon,
    href: "/project-files",
    visible: always,
    children: [
      { href: "/project-files", label: "Programs", icon: DatabaseIcon, visible: always },
      { href: "/planning/baselines", label: "Baselines", icon: LockIcon, visible: always },
      { href: "/gantt", label: "Chart", icon: GanttIcon, visible: always },
      { href: "/planning/schedule-simulation", label: "Scenario Lab", icon: SimulationIcon, visible: always },
      { href: "/export-sync-p6", label: "Export / Sync to P6", icon: DownloadIcon, visible: always },
    ],
  },
  {
    key: "execution",
    label: "Delivery",
    icon: FlagIcon,
    href: "/execution/my-desk",
    visible: always,
    children: [
      { href: "/execution/my-desk", label: "My Desk", icon: PinIcon, visible: always },
      { href: "/progress", label: "Activity Ledger", icon: ClockIcon, visible: always },
      { href: "/recovery-plan", label: "Recovery Plan", icon: TrendingUpIcon, visible: always },
      { href: "/execution/changes", label: "Changes", icon: CompareIcon, visible: always },
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
      // QSRA / Early Warnings / Resources / Recommendations: the foresight
      // layer — see backend services/risk_analysis.py, risk_signals.py,
      // risk_resources.py.
      { href: "/risk", label: "QSRA & Forecast", icon: DiceIcon, visible: always },
      { href: "/risk/register", label: "Risk Register", icon: LayersIcon, visible: always },
      { href: "/risk/early-warnings", label: "Early Warnings", icon: AlertTriangleIcon, visible: always },
      { href: "/risk/resources", label: "Resources Analysis", icon: UsersIcon, visible: always },
      { href: "/risk/recommendations", label: "Recommendations", icon: FlagIcon, visible: always },
      { href: "/risk/matrix", label: "Risk Matrix", icon: GridIcon, visible: always },
      { href: "/risk/mitigation-plans", label: "Mitigation Plans", icon: ShieldCheckIcon, visible: always },
    ],
  },
  {
    key: "reporting",
    label: "Reports",
    icon: BarChartIcon,
    href: "/reporting/reports",
    visible: always,
    // Progress Reports / Schedule Reports / Custom Reports / Project Dashboard
    // were four empty slots for the same thing: a report you assemble and hand
    // to someone. They are one page now, and the old routes redirect to it.
    children: [
      { href: "/reporting/reports", label: "Reports", icon: BarChartIcon, visible: always },
      // A status rollup is something you report, not something you act on —
      // it moved here from Delivery (route unchanged).
      { href: "/execution/project-status", label: "Project Status", icon: GridIcon, visible: always },
      { href: "/reporting/float-path", label: "Float Path", icon: TrendingUpIcon, visible: always },
      { href: "/evm", label: "S-Curve & EVM", icon: TrendingUpIcon, visible: always },
      { href: "/dcma", label: "DCMA 14-Point", icon: ShieldCheckIcon, visible: always },
      { href: "/logic-diff", label: "Logic Diff", icon: CompareIcon, visible: always },
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
    ],
  },
];

const ROLE_LABEL: Record<string, string> = {
  company_admin: "Company Admin",
  company_employee: "Employee",
};

// Below this width the sidebar is an off-canvas drawer (globals.css uses the
// same 900px breakpoint).
const MOBILE_QUERY = "(max-width: 900px)";

// The viewer's expanded/collapsed sidebar choice, per browser. The attribute
// on <html> is what the CSS reads; the inline script below sets it before the
// first paint so a collapsed rail doesn't flash open on a full page load.
const SIDEBAR_STORAGE_KEY = "poko:sidebar";
const SIDEBAR_BOOT_SCRIPT = `try{if(localStorage.getItem(${JSON.stringify(
  SIDEBAR_STORAGE_KEY
)})==="collapsed")document.documentElement.setAttribute("data-sidebar","collapsed")}catch(e){}`;

function readSidebarCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "collapsed";
  } catch {
    return false;
  }
}

function writeSidebarCollapsed(collapsed: boolean) {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "collapsed" : "expanded");
  } catch {
    // Storage unavailable (private mode, blocked site data): the choice just
    // lasts for this page view.
  }
}

function applySidebarAttribute(collapsed: boolean) {
  if (collapsed) document.documentElement.setAttribute("data-sidebar", "collapsed");
  else document.documentElement.removeAttribute("data-sidebar");
}

// Exact match, not a prefix check: several sibling routes share a prefix
// (e.g. /risk and /risk/register), and every destination here is a static
// leaf route, so there's no nested-segment case that would need startsWith.
function isActiveHref(pathname: string | null, href: string): boolean {
  return pathname === href;
}

// Small lock marker on gated sidebar sections while the selected project has
// no baseline. Rendered inside <ProjectProvider>, so it can read the context.
function GatedTabLock() {
  const { project, baselineReady } = useProjectContext();
  if (!project || baselineReady !== false) return null;
  return <LockIcon className="icon" style={{ width: 12, height: 12, opacity: 0.7 }} />;
}

// Browser tab title: "Page · Project · POKO". Rendered inside <ProjectProvider>
// (same pattern as GatedTabLock) so it can read the selected project.
function DocumentTitle({ label }: { label: string | null }) {
  const { project } = useProjectContext();
  useEffect(() => {
    document.title = [label, project?.name, "POKO"].filter(Boolean).join(" · ");
  }, [label, project?.name]);
  return null;
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

  const pageLabel = activeSection
    ? activeSection.children.find((c) => c.href === pathname)?.label ?? activeSection.label
    : null;

  const navSections: SideNavSection[] = visibleSections.map((section) => ({
    key: section.key,
    label: section.label,
    icon: section.icon,
    href: section.href,
    items: section.children
      .filter((child) => child.visible(user))
      .map((child) => ({ href: child.href, label: child.label })),
    marker: BASELINE_GATED_SECTIONS.has(section.key) ? <GatedTabLock /> : null,
  }));

  // Desktop: expanded sidebar or collapsed icon rail (remembered per viewer).
  // Below 900px: an off-canvas drawer the hamburger opens and closes.
  const [collapsed, setCollapsed] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const burgerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const stored = readSidebarCollapsed();
    setCollapsed(stored);
    applySidebarAttribute(stored);
    return () => document.documentElement.removeAttribute("data-sidebar");
  }, []);

  useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY);
    setIsMobile(mql.matches);
    function handleChange() {
      setIsMobile(mql.matches);
      setDrawerOpen(false);
    }
    mql.addEventListener("change", handleChange);
    return () => mql.removeEventListener("change", handleChange);
  }, []);

  // The drawer closes whenever the route changes.
  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!drawerOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      setDrawerOpen(false);
      burgerRef.current?.focus();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [drawerOpen]);

  function handleBurger() {
    if (window.matchMedia(MOBILE_QUERY).matches) {
      setDrawerOpen((open) => !open);
      return;
    }
    const next = !collapsed;
    setCollapsed(next);
    applySidebarAttribute(next);
    writeSidebarCollapsed(next);
  }

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  const burgerLabel = isMobile
    ? drawerOpen
      ? "Close navigation"
      : "Open navigation"
    : collapsed
      ? "Expand navigation"
      : "Collapse navigation";

  return (
    <ProjectProvider>
      <DocumentTitle label={pageLabel} />
      <div className={`tenant-shell${drawerOpen ? " drawer-open" : ""}`}>
        <script dangerouslySetInnerHTML={{ __html: SIDEBAR_BOOT_SCRIPT }} />
        <header className="a-header">
          <button
            ref={burgerRef}
            type="button"
            className="header-burger"
            aria-controls="primary-nav"
            aria-expanded={isMobile ? drawerOpen : !collapsed}
            aria-label={burgerLabel}
            title={burgerLabel}
            onClick={handleBurger}
          >
            <MenuIcon className="icon" />
          </button>

          <div className="brand">
            <div className="mark">
              <PokoGlyph />
            </div>
            <div>
              <div className="brand-name">POKO</div>
            </div>
          </div>

          <div className="header-right">
            <ProjectSwitcher />
            <div className="header-user">
              <div className="avatar" title={user?.full_name}>
                {initials}
              </div>
              <div>
                <div className="who">{user?.full_name ?? "…"}</div>
                <div className="role">{user ? (ROLE_LABEL[user.role] ?? user.role) : ""}</div>
              </div>
              <button className="signout" onClick={handleSignOut} title="Sign out" aria-label="Sign out">
                <LogOutIcon className="icon" />
              </button>
            </div>
          </div>
        </header>

        <div className="tenant-body">
          <SideNav
            id="primary-nav"
            sections={navSections}
            activeKey={activeSection?.key ?? null}
            pathname={pathname}
            rail={collapsed && !isMobile}
            onNavigate={closeDrawer}
          />
          {isMobile && drawerOpen && <div className="sidenav-backdrop" aria-hidden="true" onClick={closeDrawer} />}
          <main className="a-main">
            <BaselineGate gated={isBaselineGated(activeSection?.key, pathname)}>{children}</BaselineGate>
          </main>
        </div>
      </div>
    </ProjectProvider>
  );
}
