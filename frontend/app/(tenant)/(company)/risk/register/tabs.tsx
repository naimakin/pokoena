"use client";

import { PageTabs } from "@/components/risk/PageTabs";
import { RiskMatrixView } from "@/components/risk/RiskMatrixView";
import { RiskRegisterView } from "@/components/risk/RiskRegisterView";

// The matrix is a view of the register, not a page of its own.
export function RegisterTabs({ initial }: { initial?: string }) {
  return (
    <PageTabs
      tabs={[
        { key: "list", label: "Register" },
        { key: "matrix", label: "Matrix" },
      ]}
      initial={initial}
      param="view"
      render={(key, strip) => (key === "matrix" ? <RiskMatrixView tabs={strip} /> : <RiskRegisterView tabs={strip} />)}
    />
  );
}
