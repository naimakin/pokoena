import type { ReactNode } from "react";

// Page- or card-level empty state: optional drawing (components/illustrations),
// a title, one sentence and an optional action. In-table "no rows" cases keep the
// plain .empty-state line instead.
export function EmptyState({
  art,
  title,
  body,
  action,
}: {
  art?: ReactNode;
  title: string;
  body?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-block">
      {art}
      <div className="empty-title">{title}</div>
      {body && <p className="empty-body">{body}</p>}
      {action && <div className="empty-action">{action}</div>}
    </div>
  );
}
