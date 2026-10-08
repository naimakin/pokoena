import { redirect } from "next/navigation";

// Renamed to /chart; kept so existing links don't 404.
export default function Page() {
  redirect("/chart");
}
