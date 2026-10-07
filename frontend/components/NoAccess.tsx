import Link from "next/link";
import { EmptyState } from "@/components/EmptyState";
import { LockIcon } from "@/components/icons";

/** Shown instead of a page the signed-in user's roles don't open (a direct
 *  URL or an old bookmark — the menus never link there). The page itself
 *  never mounts, so it fires none of its API calls. */
export function NoAccess({ homeHref, homeLabel }: { homeHref: string; homeLabel: string }) {
  return (
    <div className="a-content">
      <div className="card">
        <EmptyState
          art={<LockIcon className="icon-lg" style={{ color: "var(--text-muted)" }} />}
          title="You don't have access to this page"
          body="Your role doesn't include it. Ask a company admin if you need it."
          action={
            <Link className="btn btn-primary btn-sm" href={homeHref} style={{ textDecoration: "none" }}>
              Go to {homeLabel}
            </Link>
          }
        />
      </div>
    </div>
  );
}
