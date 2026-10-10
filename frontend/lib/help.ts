// The short "?" explanations (components/HelpTip.tsx). One place for every
// page and card, so the wording stays consistent: what it shows and how to
// read it, in one or two sentences — never a manual.

export interface HelpEntry {
  title: string;
  body: string;
}

export const HELP = {
  // --- pages ------------------------------------------------------------------
  "page.dashboard": {
    title: "Dashboard",
    body: "The project at a glance against its locked baseline. Use Configure to choose and order the cards.",
  },
  "page.my-desk": {
    title: "My Desk",
    body: "Your own corner: approvals waiting on you, @mentions, pinned activities and private notes. Only you see it.",
  },
  "page.portfolio": {
    title: "Projects Dashboard",
    body: "Every project you can open, side by side. Click a phase, a status row or a project to narrow the page down.",
  },
  "page.projects": {
    title: "Projects",
    body: "All projects in your company. Open one to make it the current project across the app.",
  },
  "page.programme-files": {
    title: "Programme Files",
    body: "Upload P6 .xer updates here. The newest upload becomes the live schedule; each one is kept so updates can be compared.",
  },
  "page.baselines": {
    title: "Baselines",
    body: "The frozen plan every update is measured against. Lock it once the programme is agreed; variance and SPI start from here.",
  },
  "page.wbs": {
    title: "WBS",
    body: "The programme's work breakdown structure as imported from P6. Pick an earlier upload to see its tree.",
  },
  "page.activity-workspace": {
    title: "Activity Workspace",
    body: "Every activity in one grid, with an optional Gantt. Filter, group by WBS and enter progress; changes save straight away.",
  },
  "page.recovery-plan": {
    title: "Recovery Plan",
    body: "Activities that slipped between two updates. Each needs a root cause and actions; reviewers acknowledge the plan.",
  },
  "page.scenario-lab": {
    title: "Scenario Lab",
    body: "Try what-ifs on a copy of the current programme — durations, logic, dates — and see what moves. The live schedule is never touched.",
  },
  "page.export-sync": {
    title: "Export / Sync to P6",
    body: "Download the programme as a .xer to carry Poko's progress back into P6. Exports (EXP-n) and imports (UPD-n) are logged here.",
  },
  "page.qsra": {
    title: "QSRA & Forecast",
    body: "A Monte Carlo run on the live logic with the risk register applied. It answers how likely each finish date is and what drives the spread.",
  },
  "page.risk-register": {
    title: "Risk Register",
    body: "The project's risks with probability, impact and owner. Score = probability × impact; high scores feed QSRA and the Dashboard.",
  },
  "page.early-warnings": {
    title: "Early Warnings",
    body: "Signals read across schedule updates that tend to move before the finish date does — eroding float, slipping starts, stalled work.",
  },
  "page.resources": {
    title: "Resources Analysis",
    body: "Planned, earned and remaining work per week, and the finish date the crew's demonstrated production supports.",
  },
  "page.mitigation": {
    title: "Mitigation",
    body: "Actions to bring risks down, and suggestions drawn from QSRA and the schedule. Track each to an owner and a date.",
  },
  "page.project-status": {
    title: "Project Status",
    body: "Progress, risk and quality verdicts for the current update, and which activities need attention first. Filters narrow it to a WBS or code.",
  },
  "page.evm": {
    title: "S-Curve & EVM",
    body: "Earned value in labor hours against the locked baseline: planned (PV), earned (EV) and actual (AC), and the indices built from them.",
  },
  "page.schedule-quality": {
    title: "Schedule Quality",
    body: "The DCMA 14-point check on the current programme, plus Poko's own logic checks. Each check shows its target and the failing activities.",
  },
  "page.float-path": {
    title: "Float Path",
    body: "The chains of logic driving one activity, ranked. Path 1 holds the date today; the next paths are what will hold it next.",
  },
  "page.update-comparison": {
    title: "Update Comparison",
    body: "What changed between two schedule updates: activities added, removed or moved, and logic changes.",
  },
  "page.report-builder": {
    title: "Report Builder",
    body: "Choose the blocks a report contains and save it as a format. Reports are generated from the current programme every time you open them.",
  },
  "page.subcontractors": {
    title: "Subcontractors",
    body: "A scope is the part of the programme a subcontractor sees and updates, picked by WBS and activity codes.",
  },
  "page.users": {
    title: "Users",
    body: "Invite people, choose the projects or scopes they reach, and the roles that decide what they can do.",
  },

  // --- dashboard cards ----------------------------------------------------------
  "dash.current-update": {
    title: "Current update",
    body: "The schedule the numbers come from, and its data date — the day progress was measured to.",
  },
  "dash.next-update": {
    title: "Next update",
    body: "When the next schedule update is due, estimated from the usual gap between past updates.",
  },
  "dash.this-update": {
    title: "This update",
    body: "Activities that started or finished between the previous update and this one, and how many are complete overall.",
  },
  "dash.recovery": {
    title: "Recovery plans",
    body: "Activities that slipped past the threshold since the last update and still need an acknowledged recovery plan.",
  },
  "dash.kpi-delay": {
    title: "Delay",
    body: "Forecast finish minus baseline finish, in calendar days. Positive means the project is running late.",
  },
  "dash.kpi-spi": {
    title: "SPI",
    body: "Schedule performance: work done ÷ work planned by the data date. 1.00 is on plan; below 0.95 is behind.",
  },
  "dash.hours": {
    title: "Labor hours",
    body: "Actual labor hours as a share of the budget (P6 units % complete). The tick is where the baseline planned to be by the data date.",
  },
  "dash.cost": {
    title: "Cost",
    body: "Money spent as a share of the budget, from P6 resource costs. The tick is the spend the baseline planned by the data date.",
  },
  "dash.time-vs-work": {
    title: "Time vs work",
    body: "Outer ring: share of the baseline duration already elapsed. Inner ring: share of the work done. Work behind time means a slip.",
  },
  "dash.s-curve": {
    title: "Progress curve",
    body: "Cumulative % complete over time: baseline plan, actual per update, and the current forecast. The gap at the data date is the lag.",
  },
  "dash.monthly": {
    title: "Monthly progress",
    body: "Hours (or cost) planned and achieved each month, with the cumulative curves on top. Hover a month for the numbers.",
  },
  "dash.by-group": {
    title: "Progress by WBS / code",
    body: "Planned-to-date vs actual for each WBS branch or activity code value — shows where the shortfall sits.",
  },
  "dash.behind-plan": {
    title: "Behind plan",
    body: "Unfinished activities more than 5 points behind the baseline's planned % at the data date, worst first.",
  },
  "dash.budget-actual": {
    title: "Budget vs actual",
    body: "Budget at completion against actual to date, with the cumulative trend. Remaining is what P6 still has to spend.",
  },
  "dash.timeline": {
    title: "Project timeline",
    body: "Each month shaded by how critical the work active in it is; the strip below marks negative-float (red) and zero-float (amber) months. Click a month for its activities.",
  },
  "dash.critical": {
    title: "Most critical activities",
    body: "Unfinished activities with the highest Criticality Score — float, duration, free float and site risk combined.",
  },
  "dash.health": {
    title: "Project health",
    body: "A 0–100 score from schedule and cost performance, the critical path, overdue work and submissions. Each factor links to its detail.",
  },
  "dash.risks": {
    title: "Top risks",
    body: "The three strongest signals right now — high-scoring register risks and schedule issues such as negative float.",
  },
  "dash.scopes": {
    title: "Scope submissions",
    body: "Each subcontractor's scope, whether they submitted this update period, and their average % complete.",
  },

  // --- portfolio ----------------------------------------------------------------
  "pf.phase": {
    title: "Projects by phase",
    body: "How many projects are complete, running, not started or not yet baselined. Click a phase to filter the page.",
  },
  "pf.hours": {
    title: "Portfolio labor hours",
    body: "All baselined projects' labor hours added up: actual vs budget, with the plan tick for the data dates.",
  },
  "pf.performance": {
    title: "Portfolio performance",
    body: "SPI across the portfolio, weighted by labor hours, so large projects count more than small ones.",
  },
  "pf.progress": {
    title: "Progress by project",
    body: "One bar per project: the bar is actual, the tick is planned by its data date. Click a name to open that project.",
  },
  "pf.status": {
    title: "Overall status",
    body: "Projects grouped by progress, risk and quality verdicts. Click a row to filter the scorecard and timelines.",
  },
  "pf.scorecard": {
    title: "Portfolio scorecard",
    body: "Key schedule numbers for every project. Sort by any column; click a project to open its dashboard.",
  },
  "pf.timelines": {
    title: "Portfolio timelines",
    body: "Each month shaded by the criticality of the work active in it — darker months are where the risk concentrates.",
  },
  "pf.critical": {
    title: "Most critical activities",
    body: "Unfinished activities with the highest Criticality Score across all projects — float, duration and logic combined.",
  },

  // --- risk -----------------------------------------------------------------------
  "qsra.probability": {
    title: "Probability of finishing by date",
    body: "Share of simulated runs that finish on or before each date. P50 is a coin flip; P80 is the usual commitment level.",
  },
  "qsra.cpm-to-p80": {
    title: "From the CPM date to P80",
    body: "The working days each layer of uncertainty adds on the way from the deterministic CPM date to the P80 finish.",
  },
  "qsra.drivers": {
    title: "What drives the risk",
    body: "The risks and activities that widen the finish range most. Act on the top of this list first.",
  },
  "qsra.sensitivity": {
    title: "Activity sensitivity",
    body: "Criticality is the share of runs where an activity drives the finish; SSI also weighs how much its duration varies.",
  },
  "qsra.recommendations": {
    title: "Recommendations",
    body: "Suggested actions drawn from this run's drivers. Send them to Mitigation to track.",
  },
  "qsra.confidence": {
    title: "Confidence across runs",
    body: "P50 and P80 from each saved run, so you can see whether confidence in the finish is improving or eroding.",
  },
  "res.two-forecasts": {
    title: "Two forecasts",
    body: "One asks whether the schedule's dates are achievable; the other where the job lands at the production rate shown so far.",
  },
  "res.weekly": {
    title: "Units per week",
    body: "Work planned, earned and remaining per week. A remaining hump above anything achieved so far is a warning.",
  },
  "res.production": {
    title: "Production between updates",
    body: "Work earned between consecutive updates — the crew's demonstrated rate, which the forecast extends.",
  },
  "res.by-resource": {
    title: "By resource",
    body: "The same view per resource, to see which crew or trade is falling behind.",
  },

  // --- other cards ----------------------------------------------------------------
  "dcma.overall": {
    title: "Overall schedule quality",
    body: "Share of DCMA checks the programme passes. Poko's own checks are listed separately and don't count toward the score.",
  },
  "status.summary": {
    title: "Project summary",
    body: "Progress is read from SPI, Risk from negative float, finish slip and the recovery index, Quality from the DCMA score.",
  },
  "status.priorities": {
    title: "Priorities",
    body: "Activities split by importance (5 days of float or less) and urgency (in progress or due within 4 weeks). Start with Focus On.",
  },
  "desk.waiting": {
    title: "Waiting on you",
    body: "Approvals, revisions and update deadlines that need your action, across your projects.",
  },
  "desk.mentions": {
    title: "Mentions",
    body: "Comments and recovery plans where someone tagged you with @. Opening one marks it read.",
  },
  "desk.pins": {
    title: "Pinned activities",
    body: "Activities you pinned, and how their dates moved since you pinned them and since the previous update.",
  },
  "desk.watch": {
    title: "Worth watching",
    body: "Activities on negative float, critical, or starting within 14 days that you haven't pinned yet.",
  },
  "desk.notes": {
    title: "Private notes",
    body: "Notes only you can see, optionally tied to an activity.",
  },
  "evm.history": {
    title: "Baseline history",
    body: "Every baseline locked on this project. Only the active one is used for EVM, variance and SPI.",
  },
  "baselines.programme": {
    title: "Baseline programme",
    body: "The schedule the active baseline was locked from — its dates and budgets are frozen.",
  },
  "baselines.resources": {
    title: "Resources in this baseline",
    body: "Labor, equipment and material budgets frozen with the baseline. Labor hours drive EVM and the hours gauges.",
  },
  "files.history": {
    title: "Import history",
    body: "Every .xer uploaded to this project. The current one feeds the live schedule; edit an entry to relabel it or mark it as baseline.",
  },
  "changes.added": { title: "Added activities", body: "Activities in the newer update that the older one didn't have." },
  "changes.removed": { title: "Removed activities", body: "Activities in the older update that are gone from the newer one." },
  "changes.modified": {
    title: "Modified activities",
    body: "Activities whose dates, duration, status or float changed between the two updates.",
  },
  "changes.logic": {
    title: "Logic changes",
    body: "Relationships added, removed or changed in type or lag between the two updates.",
  },
} satisfies Record<string, HelpEntry>;

export type HelpKey = keyof typeof HELP;
