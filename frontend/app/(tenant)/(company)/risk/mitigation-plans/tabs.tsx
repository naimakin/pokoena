"use client";

import { MitigationPlansView } from "@/components/risk/MitigationPlansView";
import { PageTabs } from "@/components/risk/PageTabs";
import { RecommendationsView } from "@/components/risk/RecommendationsView";

// What the rules suggest and the plans that answer them: one job, two tabs.
export function MitigationTabs({ initial }: { initial?: string }) {
  return (
    <PageTabs
      tabs={[
        { key: "plans", label: "Mitigation plans" },
        { key: "recommendations", label: "Recommendations" },
      ]}
      initial={initial}
      param="tab"
      render={(key, strip) =>
        key === "recommendations" ? <RecommendationsView tabs={strip} /> : <MitigationPlansView tabs={strip} />
      }
    />
  );
}
