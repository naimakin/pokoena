import Link from "next/link";
import { PageShell } from "@/components/PageShell";
import { EmptyState } from "@/components/EmptyState";
import { DraftingIllo } from "@/components/illustrations";

// The PlannedFeature page. Planned routes stay reachable (the top-bar menu hides
// them — see SHOW_PLANNED in app/(tenant)/(company)/layout.tsx) and point at the
// pages that already cover part of the job. Keys match each caller's `label`.
type Planned = { section: string; useToday: { href: string; label: string }[] };
const PLANNED: Record<string, Planned> = {
  "Portfolio Dashboard": {
    section: "Portfolio",
    useToday: [
      { href: "/projects", label: "Projects" },
      { href: "/dashboard", label: "Dashboard" },
    ],
  },
  Programs: { section: "Portfolio", useToday: [{ href: "/projects", label: "Projects" }] },
  Milestones: {
    section: "Planning",
    useToday: [
      { href: "/gantt", label: "Schedule" },
      { href: "/reporting/float-path", label: "Float Path" },
    ],
  },
  "AI Schedule Builder": { section: "Planning", useToday: [{ href: "/project-files", label: "Program Library" }] },
  Documents: { section: "Planning", useToday: [{ href: "/project-files", label: "Program Library" }] },
  "My Focus": {
    section: "Execution",
    useToday: [
      { href: "/progress", label: "Project Activities" },
      { href: "/risk/early-warnings", label: "Early Warnings" },
    ],
  },
  Lookahead: {
    section: "Execution",
    useToday: [
      { href: "/gantt", label: "Schedule" },
      { href: "/progress", label: "Project Activities" },
    ],
  },
  Issues: {
    section: "Execution",
    useToday: [
      { href: "/execution/changes", label: "Changes" },
      { href: "/recovery-plan", label: "Recovery Plan" },
    ],
  },
  "Update Period Control": { section: "Execution", useToday: [{ href: "/dashboard", label: "Dashboard" }] },
  "AI Assistant": { section: "AI", useToday: [{ href: "/reporting/reports", label: "Reports" }] },
  "Schedule Generator": { section: "AI", useToday: [{ href: "/project-files", label: "Program Library" }] },
  "Progress Analysis": {
    section: "AI",
    useToday: [
      { href: "/execution/project-status", label: "Project Status" },
      { href: "/evm", label: "S-Curve & EVM" },
    ],
  },
  "Delay Analysis": {
    section: "AI",
    useToday: [
      { href: "/logic-diff", label: "Logic Diff" },
      { href: "/execution/changes", label: "Changes" },
    ],
  },
  "Risk Analysis": {
    section: "AI",
    useToday: [
      { href: "/risk", label: "QSRA & Forecast" },
      { href: "/risk/register", label: "Risk Register" },
    ],
  },
  "AI Insights": {
    section: "AI",
    useToday: [
      { href: "/risk/early-warnings", label: "Early Warnings" },
      { href: "/risk/recommendations", label: "Recommendations" },
    ],
  },
  Roles: { section: "Administration", useToday: [{ href: "/user-management", label: "Users" }] },
  Contractors: { section: "Administration", useToday: [{ href: "/user-management", label: "Users" }] },
  Teams: { section: "Administration", useToday: [{ href: "/user-management", label: "Users" }] },
  Settings: { section: "Administration", useToday: [{ href: "/administration/profile", label: "My Profile" }] },
};

export function ComingSoon({ label, description }: { label: string; description: string }) {
  const entry = PLANNED[label];
  return (
    <PageShell
      section={entry?.section ?? "POKO"}
      title={label}
      desc={description}
      status={<span className="chip chip-neutral">Planned</span>}
    >
      <div className="card">
        <EmptyState
          art={<DraftingIllo />}
          title="This page is planned"
          body={
            entry ? "It isn't available yet. Until it is, these pages cover part of the job:" : "It isn't available yet."
          }
          action={entry?.useToday.map((l) => (
            <Link key={l.href} className="btn btn-secondary btn-sm" href={l.href}>
              {l.label}
            </Link>
          ))}
        />
      </div>
    </PageShell>
  );
}

export { ComingSoon as PlannedFeature };
