import type { Capability, User } from "@/lib/types";

/** True if the user holds ANY of `caps`. Capabilities come from /auth/me —
 *  the backend owns the role → capability mapping (models/user_tenant_role.py)
 *  and enforces it on every route; this only decides what to show. */
export function can(user: User | null | undefined, ...caps: Capability[]): boolean {
  if (!user) return false;
  if (user.role === "company_admin") return true;
  const held = user.capabilities ?? [];
  return caps.some((c) => held.includes(c));
}
