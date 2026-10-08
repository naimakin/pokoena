import { redirectToWorkspace } from "@/components/workspace/redirect";

// Merged into Programme > Activity Workspace; kept so existing links and
// bookmarks still land there, query string included.
export default function Page({ searchParams }: { searchParams: Record<string, string | string[] | undefined> }) {
  redirectToWorkspace(searchParams);
}
