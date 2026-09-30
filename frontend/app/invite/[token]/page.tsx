"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { PokoGlyph } from "@/components/brand";
import type { InvitePreview, TenantRole, User } from "@/lib/types";

const ROLE_HOME: Record<TenantRole, string> = {
  company_admin: "/dashboard",
  company_employee: "/dashboard",
  subcontractor: "/scope",
};

const ROLE_LABEL: Record<TenantRole, string> = {
  company_admin: "Company Admin",
  company_employee: "Company Employee",
  subcontractor: "Subcontractor",
};

export default function InviteAcceptPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const token = params.token;

  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [password, setPassword] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api
      .get<InvitePreview>(`/invites/${token}`)
      .then(setPreview)
      .catch((err) => setPreviewError(err instanceof ApiError ? err.message : "This invite link is invalid."))
      .finally(() => setLoading(false));
  }, [token]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      const user = await api.post<User>(`/invites/${token}/accept`, { password });
      router.push(ROLE_HOME[user.role] ?? "/login");
      router.refresh();
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Failed to accept this invite.");
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="login-page">
        <p className="page-desc">Loading…</p>
      </div>
    );
  }

  if (previewError || !preview) {
    return (
      <div className="login-page">
        <div className="card login-card">
          <div className="login-error">{previewError ?? "This invite link is invalid."}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={handleSubmit}>
        <div className="login-brand">
          <div className="mark">
            <PokoGlyph />
          </div>
          <div>
            <div className="login-title">Welcome, {preview.full_name || preview.email}</div>
            <div className="login-sub">
              {preview.email} · {ROLE_LABEL[preview.role]}
              {preview.title ? ` · ${preview.title}` : ""}
            </div>
            <div className="login-sub">Join {preview.tenant_name}</div>
          </div>
        </div>

        {submitError && <div className="login-error">{submitError}</div>}

        <div className="field">
          <label htmlFor="password">Set a password</label>
          <input
            id="password"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button className="btn btn-primary btn-block" type="submit" disabled={submitting}>
          {submitting ? "Setting up your account…" : "Accept invite & sign in"}
        </button>
      </form>
    </div>
  );
}
