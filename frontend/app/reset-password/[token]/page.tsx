"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { PokoGlyph } from "@/components/brand";
import type { PasswordResetPreview } from "@/lib/types";

export default function ResetPasswordPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const token = params.token;

  const [preview, setPreview] = useState<PasswordResetPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [password, setPassword] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    api
      .get<PasswordResetPreview>(`/reset-password/${token}`)
      .then(setPreview)
      .catch((err) => setPreviewError(err instanceof ApiError ? err.message : "This reset link is invalid."))
      .finally(() => setLoading(false));
  }, [token]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      const result = await api.post<PasswordResetPreview>(`/reset-password/${token}`, { password });
      setDone(true);
      setTimeout(() => {
        router.push(result.is_platform_admin ? "/platform-admin/login" : "/login");
        router.refresh();
      }, 1500);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Failed to reset your password.");
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
          <div className="login-error">{previewError ?? "This reset link is invalid."}</div>
        </div>
      </div>
    );
  }

  if (done) {
    return (
      <div className="login-page">
        <div className="card login-card">
          <div className="login-title">Password updated</div>
          <div className="login-sub">Taking you to sign in…</div>
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
            <div className="login-title">Reset your password</div>
            <div className="login-sub">{preview.email}</div>
          </div>
        </div>

        {submitError && <div className="login-error">{submitError}</div>}

        <div className="field">
          <label htmlFor="password">New password</label>
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
          {submitting ? "Saving…" : "Set new password"}
        </button>
      </form>
    </div>
  );
}
