"use client";

import Link from "next/link";
import type { RiskRecommendation } from "@/lib/types";

const CHIP = { red: "chip-crit", amber: "chip-warn", info: "chip-info" } as const;
const LABEL = { red: "Act now", amber: "Watch", info: "Note" } as const;

// Severity is carried by the chip's text as well as its color — never color alone.
export function RecommendationList({ items, empty }: { items: RiskRecommendation[]; empty: string }) {
  if (items.length === 0) return <p className="empty-state" style={{ padding: "1rem 1.1rem" }}>{empty}</p>;
  return (
    <div className="rec-list">
      {items.map((r) => (
        <div key={r.id} className="rec-item">
          <span className={`chip ${CHIP[r.severity]}`}>{LABEL[r.severity]}</span>
          <div>
            <div className="actid" style={{ marginBottom: ".15rem" }}>{r.area}</div>
            <div>{r.message}</div>
          </div>
          <Link href={r.link} className="btn btn-ghost btn-sm">
            Open
          </Link>
        </div>
      ))}
    </div>
  );
}
