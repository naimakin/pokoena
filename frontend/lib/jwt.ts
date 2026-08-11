import { jwtVerify } from "jose";
import type { TenantRole } from "@/lib/types";

// Edge-runtime compatible: this file is imported from both middleware.ts (Next's
// Edge runtime — no `fs`/Node built-ins) and lib/auth.ts (Server Components,
// full Node runtime). `jose` works in both; keep it that way — don't add
// anything here that only runs under Node.

const encoder = new TextEncoder();

function getSecretKey(): Uint8Array {
  const secret = process.env.JWT_SECRET;
  if (!secret) {
    throw new Error("JWT_SECRET is not set");
  }
  return encoder.encode(secret);
}

export interface TenantAccessPayload {
  sub: string;
  token_type: "tenant_access";
  tenant_id: string;
  role: TenantRole;
  scope_ids: string[];
}

export interface PlatformAccessPayload {
  sub: string;
  token_type: "platform_access";
}

export type AccessTokenPayload = TenantAccessPayload | PlatformAccessPayload;

/** Verifies signature + expiry against the backend's HS256 secret. Returns
 * null on any failure (missing/expired/malformed/wrong-algorithm token) —
 * callers treat that identically to "not authenticated", never distinguishing
 * why, so there's nothing here for a caller to misuse. */
export async function verifyAccessToken(token: string): Promise<AccessTokenPayload | null> {
  try {
    const { payload } = await jwtVerify(token, getSecretKey(), { algorithms: ["HS256"] });
    if (payload.token_type === "tenant_access" || payload.token_type === "platform_access") {
      return payload as unknown as AccessTokenPayload;
    }
    return null;
  } catch {
    return null;
  }
}
