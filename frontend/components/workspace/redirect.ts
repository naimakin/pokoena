import { redirect } from "next/navigation";

export const WORKSPACE_HREF = "/activity-workspace";

type SearchParams = Record<string, string | string[] | undefined>;

/** Server-side redirect to Activity Workspace that keeps the query string
 *  (?q= from the header search, ?filter=critical|overdue from the dashboard). */
export function redirectToWorkspace(searchParams: SearchParams | undefined): never {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams ?? {})) {
    if (Array.isArray(value)) value.forEach((v) => qs.append(key, v));
    else if (value !== undefined) qs.append(key, value);
  }
  const query = qs.toString();
  redirect(query ? `${WORKSPACE_HREF}?${query}` : WORKSPACE_HREF);
}
