import { redirect } from "next/navigation";

export default function RootPage() {
  // middleware.ts handles this redirect by role in normal operation; this is
  // just the fallback if middleware is ever bypassed.
  redirect("/login");
}
