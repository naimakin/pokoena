"use client";

import { ActivityChangesView } from "@/components/comparison/ActivityChangesView";
import { LogicDiffView } from "@/components/comparison/LogicDiffView";
import { PageTabs } from "@/components/PageTabs";

// Two updates side by side: what moved on the activities, and what changed in
// the logic between them.
export function ComparisonTabs({ initial }: { initial?: string }) {
  return (
    <PageTabs
      tabs={[
        { key: "activities", label: "Activities" },
        { key: "logic", label: "Logic" },
      ]}
      initial={initial}
      param="tab"
      render={(key, strip) => (key === "logic" ? <LogicDiffView tabs={strip} /> : <ActivityChangesView tabs={strip} />)}
    />
  );
}
