"use client";

import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { LogOutIcon } from "@/components/icons";

export function PlatformSignOutButton() {
  const router = useRouter();

  async function handleSignOut() {
    await api.post("/platform-auth/logout");
    router.push("/platform-admin/login");
    router.refresh();
  }

  return (
    <button className="signout" onClick={handleSignOut} title="Sign out" aria-label="Sign out">
      <LogOutIcon className="icon" />
    </button>
  );
}
