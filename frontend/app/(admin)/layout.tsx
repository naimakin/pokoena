"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import {
  BarChartIcon,
  BuildingIcon,
  CalendarIcon,
  GridIcon,
  LayersIcon,
  UploadCloudIcon,
  XIcon,
} from "@/components/icons";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: GridIcon },
  { href: "/review-queue", label: "Change Review Queue", icon: LayersIcon },
];

export default function AdminLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    api
      .get<User>("/auth/me")
      .then(setUser)
      .catch(() => router.push("/login"));
  }, [router]);

  async function handleSignOut() {
    await api.post("/auth/logout");
    router.push("/login");
    router.refresh();
  }

  const initials = user?.full_name
    ? user.full_name
        .split(" ")
        .map((part) => part[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "";

  return (
    <div className="app-shell">
      <aside className="a-sidebar">
        <div className="brand">
          <div className="mark">
            <BuildingIcon className="icon" />
          </div>
          <div>
            <div className="brand-name">POKO</div>
            <div className="brand-sub">on Primavera P6</div>
          </div>
        </div>

        <nav>
          <div className="nav-group-label">Riverside Logistics Park</div>
          <div className="navlist">
            {NAV.map(({ href, label, icon: Icon }) => (
              <Link key={href} href={href} className={`navitem${pathname?.startsWith(href) ? " active" : ""}`}>
                <Icon className="icon" />
                <span>{label}</span>
              </Link>
            ))}
            <span className="navitem disabled">
              <CalendarIcon className="icon" />
              <span>Update Period Control</span>
              <span className="soon">Next</span>
            </span>
            <span className="navitem disabled">
              <BarChartIcon className="icon" />
              <span>Analysis Results</span>
              <span className="soon">Next</span>
            </span>
            <span className="navitem disabled">
              <UploadCloudIcon className="icon" />
              <span>Export / Sync to P6</span>
              <span className="soon">Next</span>
            </span>
          </div>
        </nav>

        <div className="a-foot">
          <div className="avatar">{initials}</div>
          <div>
            <div className="who">{user?.full_name ?? "…"}</div>
            <div className="role">{user?.role === "admin" ? "Project Controls" : "Viewer"}</div>
          </div>
          <button className="signout" onClick={handleSignOut} title="Sign out" aria-label="Sign out">
            <XIcon className="icon" />
          </button>
        </div>
      </aside>

      <main className="a-main">{children}</main>
    </div>
  );
}
