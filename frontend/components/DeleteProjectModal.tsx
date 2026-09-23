"use client";

import { useEffect, useState } from "react";
import { AlertTriangleIcon } from "@/components/icons";
import type { Project } from "@/lib/types";

export function DeleteProjectModal({
  project,
  deleting,
  onCancel,
  onConfirm,
}: {
  project: Project | null;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: (confirmCode: string) => void;
}) {
  const [typed, setTyped] = useState("");

  useEffect(() => {
    if (project) setTyped("");
  }, [project]);

  if (!project) return null;

  const matches = typed.trim() === project.code;

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="modal">
        <div className="modal-head">
          <AlertTriangleIcon className="icon-lg" style={{ color: "var(--crit)" }} />
          <div>
            <div className="modal-title">Delete project</div>
            <div className="modal-desc">
              This permanently deletes <b>{project.name}</b> and everything under it — schedule, activities,
              baselines, progress, EVM history, risk register, recovery plans, saved filters — for every user.
              This can&apos;t be undone.
            </div>
          </div>
        </div>
        <div className="modal-body">
          <div className="field">
            <label htmlFor="delete-project-confirm">
              Type <span className="mono">{project.code}</span> to confirm
            </label>
            <input
              id="delete-project-confirm"
              type="text"
              autoFocus
              autoComplete="off"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && matches && !deleting) onConfirm(typed.trim());
              }}
            />
          </div>
        </div>
        <div className="modal-foot">
          <button className="btn btn-ghost" onClick={onCancel} disabled={deleting}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            style={{ background: "var(--crit)" }}
            disabled={!matches || deleting}
            onClick={() => onConfirm(typed.trim())}
          >
            {deleting ? "Deleting…" : "Delete project permanently"}
          </button>
        </div>
      </div>
    </div>
  );
}
