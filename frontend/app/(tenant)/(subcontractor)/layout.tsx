import type { ReactNode } from "react";

// Deliberately thin — the subcontractor scope view is a distinct, minimal
// route tree (its own nested layout under (tenant), separate from the
// company admin/employee shell in (company)/layout.tsx) so a subcontractor's
// bundle and rendered page never reference dashboard/review-queue/team code
// at all. The backend's require_scope_access is still the real boundary —
// this is UI minimalism, not the security control.
export default function SubcontractorLayout({ children }: { children: ReactNode }) {
  return children;
}
