import type { ReactNode } from "react";
import { AlertTriangleIcon } from "@/components/icons";
import { EmptyState } from "@/components/EmptyState";

// The page frame every (company) page shares: a quiet section eyebrow, then the
// title, description and actions. No hooks, no "use client" — safe in server pages.
export function PageShell({
  section,
  title,
  desc,
  status,
  actions,
  children,
}: {
  section: ReactNode;
  title: ReactNode;
  desc?: ReactNode;
  status?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <>
      <div className="a-topbar">
        <span className="crumb">{section}</span>
        {status && (
          <>
            <div className="spacer" />
            {status}
          </>
        )}
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">{title}</div>
            {desc && <div className="page-desc">{desc}</div>}
          </div>
          {actions && <div className="page-actions">{actions}</div>}
        </div>
        {children}
      </div>
    </>
  );
}

// Loading / error / empty block. With a `title` it renders inside the full frame
// (topbar + head), so the chrome doesn't jump when the data arrives.
export function PageState({
  kind,
  message,
  emptyTitle,
  art,
  action,
  section,
  title,
}: {
  kind: "loading" | "error" | "empty";
  message?: ReactNode;
  emptyTitle?: string;
  art?: ReactNode;
  action?: ReactNode;
  section?: ReactNode;
  title?: ReactNode;
}) {
  const block =
    kind === "loading" ? (
      <div className="card" aria-busy="true" aria-label="Loading">
        <div className="skeleton-stack">
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      </div>
    ) : kind === "error" ? (
      <div className="banner crit" role="alert">
        <AlertTriangleIcon className="icon" />
        <span className="banner-text">{message ?? "Something went wrong."}</span>
      </div>
    ) : (
      <div className="card">
        <EmptyState art={art} title={emptyTitle ?? "Nothing here yet"} body={message} action={action} />
      </div>
    );
  return title ? (
    <PageShell section={section ?? ""} title={title}>
      {block}
    </PageShell>
  ) : (
    block
  );
}
