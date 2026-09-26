import { redirect } from "next/navigation";

// Moved under Reporting; kept so existing links don't 404.
export default function Page() {
  redirect("/reporting/float-path");
}
