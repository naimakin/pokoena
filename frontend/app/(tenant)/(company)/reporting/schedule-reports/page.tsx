import { redirect } from "next/navigation";

// Folded into the single Reports page; kept so existing links don't 404.
export default function Page() {
  redirect("/reporting/reports");
}
