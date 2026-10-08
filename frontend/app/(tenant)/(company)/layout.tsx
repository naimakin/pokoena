"use client";

import { useCallback, useEffect, useRef, useState, type ComponentType, type ReactNode, type SVGProps } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Capability, User } from "@/lib/types";
import { can } from "@/lib/permissions";
import { CurrentUserProvider } from "@/lib/user-context";
import { ProjectProvider, useProjectContext } from "@/lib/project-context";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { BaselineGate, BASELINE_GATED_SECTIONS, isBaselineGated } from "@/components/BaselineGate";
import { SideNav, type SideNavSection } from "@/components/SideNav";
import { UserMenu } from "@/components/UserMenu";
import { GlobalSearch, type SearchPage } from "@/components/GlobalSearch";
import {
  AlertTriangleIcon,
  BarChartIcon,
  BuildingIcon,
  CalendarIcon,
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
  MenuIcon,
  PinIcon,
  ShieldCheckIcon,
  SimulationIcon,
  TrendingUpIcon,
  UsersIcon,
} from "@/components/icons";
import { PokoGlyph } from "@/components/brand";
import { NoAccess } from "@/components/NoAccess";

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

// A menu item shows only when the user holds one of these capabilities
// (/auth/me; the backend enforces the same on every route). A page the user
// can't open never appears — in the sidebar, the header search or the user menu.
const need =
  (...caps: Capability[]): Visible =>
  (user) =>
    can(user, ...caps);

const isCompanyAdmin: Visible = (user) => user?.role === "company_admin";

// Where a destination is reused under more than one top section, TOP_SECTIONS
// order below decides which section is treated as "active" when that route is
// open (first match wins).
const TOP_SECTIONS: NavSection[] = [
  {
    key: "overview",
    label: "Overview",
    icon: GridIcon,
    href: "/dashboard",
    visible: always,
    children: [
      // The personal, cross-project inbox — the first stop of the day.
      { href: "/execution/my-desk", label: "My Desk", icon: PinIcon, visible: need("view_delivery") },
      { href: "/dashboard", label: "Dashboard", icon: GridIcon, visible: need("view_overview") },
      { href: "/portfolio/dashboard", label: "Portfolio Dashboard", icon: BuildingIcon, visible: need("view_overview") },
    ],
  },
  {
    key: "planning",
    label: "Programme",
    icon: CalendarIcon,
    href: "/activity-workspace",
    visible: always,
    // Programme and Delivery were one job in two menus; merged, in the order
    // the work runs. Routes are unchanged.
    children: [
      { href: "/project-files", label: "Programme Files", icon: DatabaseIcon, visible: need("view_programme") },
      { href: "/planning/baselines", label: "Baselines", icon: LockIcon, visible: need("view_programme") },
      // Activity Ledger + Chart, merged: anyone who could open either page.
      { href: "/activity-workspace", label: "Activity Workspace", icon: GanttIcon, visible: need("view_programme", "view_delivery") },
      { href: "/recovery-plan", label: "Recovery Plan", icon: TrendingUpIcon, visible: need("view_delivery") },
      { href: "/planning/schedule-simulation", label: "Scenario Lab", icon: SimulationIcon, visible: need("view_programme") },
      { href: "/export-sync-p6", label: "Export / Sync to P6", icon: DownloadIcon, visible: need("export") },
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
      { href: "/risk", label: "QSRA & Forecast", icon: DiceIcon, visible: need("view_risk") },
      { href: "/risk/register", label: "Risk Register", icon: LayersIcon, visible: need("view_risk") },
      { href: "/risk/early-warnings", label: "Early Warnings", icon: AlertTriangleIcon, visible: need("view_risk") },
      { href: "/risk/resources", label: "Resources Analysis", icon: UsersIcon, visible: need("view_risk") },
      // Register holds the matrix as a tab; Mitigation holds the recommendations.
      { href: "/risk/mitigation-plans", label: "Mitigation", icon: ShieldCheckIcon, visible: need("view_risk") },
    ],
  },
  {
    key: "reporting",
    label: "Reports",
    icon: BarChartIcon,
    href: "/execution/project-status",
    visible: always,
    // Progress Reports / Schedule Reports / Custom Reports / Project Dashboard
    // were four empty slots for the same thing: a report you assemble and hand
    // to someone. They are one page now, and the old routes redirect to it.
    children: [
      // Summary first, then the analyses, then building a report to hand on.
      { href: "/execution/project-status", label: "Project Status", icon: GridIcon, visible: need("view_reports") },
      { href: "/evm", label: "S-Curve & EVM", icon: TrendingUpIcon, visible: need("view_reports") },
      // DCMA's 14 checks plus POKO's own — more than DCMA, hence the name.
      { href: "/dcma", label: "Schedule Quality", icon: ShieldCheckIcon, visible: need("view_reports") },
      { href: "/reporting/float-path", label: "Float Path", icon: TrendingUpIcon, visible: need("view_reports") },
      // What moved between two updates: read, not acted on (route unchanged).
      { href: "/execution/changes", label: "Changes", icon: CompareIcon, visible: need("view_reports", "view_delivery") },
      { href: "/logic-diff", label: "Logic Diff", icon: CompareIcon, visible: need("view_reports") },
      { href: "/reporting/reports", label: "Report Builder", icon: BarChartIcon, visible: need("view_reports") },
    ],
  },
];

// Account and administration pages open from the user menu in the header's
// top-right corner (components/UserMenu.tsx), not the sidebar.
const ADMIN_LINKS: NavChild[] = [
  { href: "/projects", label: "Projects", icon: FolderIcon, visible: need("manage_projects") },
  { href: "/user-management", label: "Users", icon: UsersIcon, visible: need("manage_users") },
  { href: "/administration/scopes", label: "Subcontractors", icon: LayersIcon, visible: need("manage_projects") },
];

// Pages not in any menu, and what opening them needs.
const EXTRA_ROUTES: { prefix: string; visible: Visible }[] = [
  { prefix: "/planning/wbs", visible: need("view_programme") },
  { prefix: "/administration/profile", visible: always },
];

// Browser-tab labels for pages that aren't in the sidebar.
const ACCOUNT_PAGE_LABELS: Record<string, string> = {
  "/projects": "Projects",
  "/user-management": "Users",
  "/administration/scopes": "Subcontractors",
  "/administration/profile": "My Profile",
};

const ROLE_LABEL: Record<string, string> = {
  company_admin: "Company Admin",
  company_employee: "Employee",
};

function labelFor(href: string): string {
  for (const section of TOP_SECTIONS) {
    const child = section.children.find((c) => c.href === href);
    if (child) return child.label;
  }
  return ADMIN_LINKS.find((l) => l.href === href)?.label ?? ACCOUNT_PAGE_LABELS[href] ?? "your start page";
}

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

function matches(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Whether the user may open `pathname`: the most specific menu entry (or
 *  extra route) that covers it decides. Unknown routes are let through — the
 *  backend still refuses their data. */
function canOpen(user: User | null, pathname: string | null): boolean {
  if (!pathname) return true;
  const entries = [
    ...TOP_SECTIONS.flatMap((s) => s.children),
    ...ADMIN_LINKS,
    ...EXTRA_ROUTES.map((r) => ({ href: r.prefix, visible: r.visible })),
  ]
    .filter((e) => matches(pathname, e.href))
    .sort((a, b) => b.href.length - a.href.length);
  return entries.length === 0 || entries[0].visible(user);
}

/** The first page in the menu the user may open — where they land when the
 *  default (/dashboard) isn't theirs. */
function homeFor(user: User | null): string {
  for (const section of TOP_SECTIONS) {
    const child = section.children.find((c) => c.visible(user));
    if (child) return child.href;
  }
  const admin = ADMIN_LINKS.find((l) => l.visible(user));
  return admin?.href ?? "/administration/profile";
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

  // Unread @mentions for the My Desk badge — refreshed on every page change.
  const [unreadMentions, setUnreadMentions] = useState(0);
  useEffect(() => {
    if (!user) return;
    api
      .get<{ unread: number }>("/my-desk/mentions/count")
      .then((r) => setUnreadMentions(r.unread))
      .catch(() => setUnreadMentions(0));
  }, [user, pathname]);

  const allowed = user === null || canOpen(user, pathname);
  const home = homeFor(user);
  // Landing on the default page without access to it (e.g. a Users-only
  // account): go to the first page they have instead of a dead end.
  useEffect(() => {
    if (user && !allowed && pathname === "/dashboard" && home !== "/dashboard") router.replace(home);
  }, [user, allowed, pathname, home, router]);

  async function handleSignOut() {
    await api.post("/auth/logout");
    router.push("/login");
    router.refresh();
  }

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
    : (pathname ? ACCOUNT_PAGE_LABELS[pathname] : undefined) ?? null;

  // Everything the header search can jump to by name.
  const searchPages: SearchPage[] = [
    ...visibleSections.flatMap((section) =>
      section.children
        .filter((child) => child.visible(user))
        .map((child) => ({ href: child.href, label: child.label, group: section.label })),
    ),
    ...ADMIN_LINKS.filter((l) => l.visible(user)).map((l) => ({ href: l.href, label: l.label, group: "Administration" })),
    { href: "/administration/profile", label: "My Profile", group: "Account" },
  ];

  const navSections: SideNavSection[] = visibleSections.map((section) => ({
    key: section.key,
    label: section.label,
    icon: section.icon,
    href: section.href,
    items: section.children
      .filter((child) => child.visible(user))
      .map((child) => ({
        href: child.href,
        label: child.label,
        badge: child.href === "/execution/my-desk" ? unreadMentions : undefined,
      })),
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
            <GlobalSearch pages={searchPages} />
            <ProjectSwitcher manageHref={isCompanyAdmin(user) ? "/projects" : undefined} />
            <UserMenu
              user={user}
              roleLabel={user ? (ROLE_LABEL[user.role] ?? user.role) : ""}
              adminLinks={ADMIN_LINKS.filter((l) => l.visible(user)).map(({ href, label, icon }) => ({ href, label, icon }))}
              onSignOut={handleSignOut}
            />
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
            {user === null ? null : allowed ? (
              <CurrentUserProvider user={user}>
                <BaselineGate gated={isBaselineGated(activeSection?.key, pathname)}>{children}</BaselineGate>
              </CurrentUserProvider>
            ) : (
              <NoAccess homeHref={home} homeLabel={labelFor(home)} />
            )}
          </main>
        </div>
      </div>
    </ProjectProvider>
  );
}
