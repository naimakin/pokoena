import { redirect } from "next/navigation";

// Now a tab of the Risk Register; kept so existing links don't 404.
export default function Page() {
  redirect("/risk/register?view=matrix");
}
