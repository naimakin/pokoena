import { redirect } from "next/navigation";

// Now a tab of Risk > Mitigation; kept so existing links don't 404.
export default function Page() {
  redirect("/risk/mitigation-plans?tab=recommendations");
}
