import "server-only";

import { cache } from "react";
import { cookies } from "next/headers";
import { verifyAccessToken, type TenantAccessPayload } from "@/lib/jwt";

const TENANT_SESSION_COOKIE = "poko_tenant_session";
const PLATFORM_SESSION_COOKIE = "poko_platform_session";

export interface TenantAuth {
  kind: "tenant";
  userId: string;
  tenantId: string;
  role: TenantAccessPayload["role"];
  scopeIds: string[];
}

export interface PlatformAuth {
  kind: "platform";
  userId: string;
}

/**
 * Server-only "who is making this request" helper for Server Components and
 * Route Handlers — verifies the same JWT middleware.ts already checked, so
 * components can read identity/tenant context without prop-drilling it down
 * from a layout. Wrapped in React's `cache()` so multiple components calling
 * `auth()` within one request tree only verify the token once.
 *
 * This re-verification is deliberate, not redundant with middleware: Server
 * Components can be reached by more than one route (layouts, parallel routes,
 * revalidation), and trusting a header middleware set is weaker than each
 * consumer verifying the signature itself. It's the same "layer twice" logic
 * as the backend's RLS-plus-app-checks — cheap here, and it's the actual
 * security boundary for anything a Server Component fetches on the user's behalf.
 */
export const auth = cache(async (): Promise<TenantAuth | PlatformAuth | null> => {
  const cookieStore = cookies();

  const tenantToken = cookieStore.get(TENANT_SESSION_COOKIE)?.value;
  if (tenantToken) {
    const payload = await verifyAccessToken(tenantToken);
    if (payload && payload.token_type === "tenant_access") {
      return {
        kind: "tenant",
        userId: payload.sub,
        tenantId: payload.tenant_id,
        role: payload.role,
        scopeIds: payload.scope_ids,
      };
    }
  }

  const platformToken = cookieStore.get(PLATFORM_SESSION_COOKIE)?.value;
  if (platformToken) {
    const payload = await verifyAccessToken(platformToken);
    if (payload && payload.token_type === "platform_access") {
      return { kind: "platform", userId: payload.sub };
    }
  }

  return null;
});
