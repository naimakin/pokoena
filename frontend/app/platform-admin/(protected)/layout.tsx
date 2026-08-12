import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { auth } from "@/lib/auth";
import { BuildingIcon, GridIcon, BarChartIcon, UsersIcon } from "@/components/icons";
import { PlatformSignOutButton } from "./PlatformSignOutButton";

const NAV = [
  { href: "/platform-admin/tenants", label: "Tenants", icon: GridIcon },
  { href: "/platform-admin/admins", label: "Admins", icon: UsersIcon },
  { href: "/platform-admin/usage", label: "Usage", icon: BarChartIcon },
];

// Server Component: resolves identity via the server-only auth() helper (see
// lib/auth.ts) instead of a client-side "/platform-auth/me" fetch — every
// page under this group gets tenant/user context for free, with no
// prop-drilling and no loading flash. middleware.ts already redirects
// unauthenticated requests before they get this far; this is the second,
// independent check — same "layer twice" reasoning as the backend's
// RLS-plus-app-checks, and it's what actually gates this layout's own render.
export default async function PlatformProtectedLayout({ children }: { children: ReactNode }) {
  const identity = await auth();
  if (!identity || identity.kind !== "platform") {
    redirect("/platform-admin/login");
  }

  return (
    <div className="app-shell">
      <aside className="a-sidebar">
        <div className="brand">
          <div className="mark">
            <BuildingIcon className="icon" />
          </div>
          <div>
            <div className="brand-name">POKO</div>
            <div className="brand-sub">Platform Admin</div>
          </div>
        </div>

        <nav>
          <div className="nav-group-label">POKO Staff</div>
          <div className="navlist">
            {NAV.map(({ href, label, icon: Icon }) => (
              <Link key={href} href={href} className="navitem">
                <Icon className="icon" />
                <span>{label}</span>
              </Link>
            ))}
          </div>
        </nav>

        <div className="a-foot">
          <div>
            <div className="who">Platform staff</div>
            <div className="role">{identity.userId.slice(0, 8)}</div>
          </div>
          <PlatformSignOutButton />
        </div>
      </aside>

      <main className="a-main">{children}</main>
    </div>
  );
}
