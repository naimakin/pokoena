"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { PokoGlyph } from "@/components/brand";
import type { TenantRole, User } from "@/lib/types";

const ROLE_HOME: Record<TenantRole, string> = {
  company_admin: "/dashboard",
  company_employee: "/dashboard",
  subcontractor: "/scope",
};

export default function TenantLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const user = await api.post<User>("/auth/login", { email, password });
      router.push(ROLE_HOME[user.role] ?? "/login");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={handleSubmit}>
        <div className="login-brand">
          <div className="mark">
            <PokoGlyph />
          </div>
          <div>
            <div className="login-title">POKO</div>
            <div className="login-sub">Project Intelligence &amp; Execution</div>
          </div>
        </div>

        {error && <div className="login-error">{error}</div>}

        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button className="btn btn-primary btn-block" type="submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>

        <a className="login-footnote" href="/platform-admin/login">
          POKO staff sign in
        </a>
      </form>
    </div>
  );
}
