import { redirect } from "next/navigation";

// Now the Logic tab of Update Comparison; kept so existing links don't 404.
export default function Page() {
  redirect("/execution/changes?tab=logic");
}
