"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

// Next's default "This page could not be found" is a dead end for a mistyped
// or stale URL on an internal tool like this — sending people to the right
// sign-in page (platform-admin vs. tenant, based on which side of the app
// they were on) gets them somewhere useful instead.
export default function NotFound() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const target = pathname?.startsWith("/platform-admin") ? "/platform-admin/login" : "/login";
    router.replace(target);
  }, [pathname, router]);

  return (
    <div className="login-page">
      <p className="page-desc">Redirecting…</p>
    </div>
  );
}
