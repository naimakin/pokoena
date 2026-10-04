import { redirect } from "next/navigation";

// My Focus became My Desk (Execution → My Desk); old links and bookmarks land there.
export default function MyFocusPage() {
  redirect("/execution/my-desk");
}
