"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { PROJECT_ROLE_LABELS, type User } from "@/lib/types";
import { UsersIcon } from "@/components/icons";

const ROLE_LABEL: Record<string, string> = {
  company_admin: "Company Admin",
  company_employee: "Employee",
  subcontractor: "Subcontractor",
};

export default function MyProfilePage() {
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<User>("/auth/me")
      .then(setUser)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load profile."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          <b>My Profile</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">My Profile</div>
            <div className="page-desc">Your account details, as set when you were invited.</div>
          </div>
        </div>

        {loading ? (
          <p className="page-desc">Loading…</p>
        ) : error ? (
          <p className="login-error" style={{ maxWidth: 420 }}>
            {error}
          </p>
        ) : user ? (
          <div className="card" style={{ maxWidth: 480 }}>
            <div className="card-head">
              <div className="cell-flex">
                <div className="subrow-avatar" style={{ width: 36, height: 36, fontSize: ".8125rem" }}>
                  <UsersIcon className="icon" style={{ width: 16, height: 16 }} />
                </div>
                <div>
                  <div className="subname">{user.full_name}</div>
                  <div className="cell-sub">{user.email}</div>
                </div>
              </div>
            </div>
            <div className="form-grid" style={{ padding: "1rem 1.1rem" }}>
              <div className="form-row">
                <div className="field">
                  <label>Role</label>
                  <div className="page-desc" style={{ marginTop: 0 }}>
                    {ROLE_LABEL[user.role] ?? user.role}
                  </div>
                </div>
                <div className="field">
                  <label>Title</label>
                  <div className="page-desc" style={{ marginTop: 0 }}>
                    {user.title ?? "—"}
                  </div>
                </div>
              </div>
              <div className="field">
                <label>Phone</label>
                <div className="page-desc" style={{ marginTop: 0 }}>
                  {user.phone ?? "—"}
                </div>
              </div>
              {user.project_roles.length > 0 && (
                <div className="field">
                  <label>Project roles</label>
                  <div className="role-wrap" style={{ marginTop: ".3rem" }}>
                    {user.project_roles.map((role) => (
                      <span key={role} className="role-badge">
                        {PROJECT_ROLE_LABELS[role]}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}
