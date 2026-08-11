import { NextRequest, NextResponse } from "next/server";
import { verifyAccessToken } from "@/lib/jwt";
import type { TenantRole } from "@/lib/types";

// Reads the real, signed session cookie and verifies it here at the edge —
// deliberately not the old pattern of trusting an unsigned companion "role"
// cookie for routing. A forged/expired/wrong-type cookie now fails exactly
// the same signature check the backend runs, before any page even renders.

const TENANT_SESSION_COOKIE = "poko_tenant_session";
const PLATFORM_SESSION_COOKIE = "poko_platform_session";

const TENANT_ROLE_HOME: Record<TenantRole, string> = {
  company_admin: "/dashboard",
  company_employee: "/dashboard",
  subcontractor: "/scope",
};

const PLATFORM_HOME = "/platform-admin/tenants";
const PLATFORM_LOGIN = "/platform-admin/login";
const TENANT_LOGIN = "/login";

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/platform-admin")) {
    return handlePlatformArea(request, pathname);
  }
  return handleTenantArea(request, pathname);
}

async function handlePlatformArea(request: NextRequest, pathname: string): Promise<NextResponse> {
  const token = request.cookies.get(PLATFORM_SESSION_COOKIE)?.value;
  const payload = token ? await verifyAccessToken(token) : null;
  const authed = payload?.token_type === "platform_access";

  if (pathname === PLATFORM_LOGIN) {
    return authed ? NextResponse.redirect(new URL(PLATFORM_HOME, request.url)) : NextResponse.next();
  }
  if (!authed) {
    return NextResponse.redirect(new URL(PLATFORM_LOGIN, request.url));
  }
  return NextResponse.next();
}

async function handleTenantArea(request: NextRequest, pathname: string): Promise<NextResponse> {
  if (pathname.startsWith("/invite/")) {
    // Public, single-use-token-gated — no session required or checked.
    return NextResponse.next();
  }

  const token = request.cookies.get(TENANT_SESSION_COOKIE)?.value;
  const payload = token ? await verifyAccessToken(token) : null;

  let role: TenantRole | null = null;
  if (payload !== null && payload.token_type === "tenant_access") {
    role = payload.role;
  }
  const authed = role !== null;
  const home = role ? TENANT_ROLE_HOME[role] : TENANT_LOGIN;

  if (pathname === "/") {
    return NextResponse.redirect(new URL(authed ? home : TENANT_LOGIN, request.url));
  }
  if (pathname === TENANT_LOGIN) {
    return authed ? NextResponse.redirect(new URL(home, request.url)) : NextResponse.next();
  }
  if (!authed) {
    return NextResponse.redirect(new URL(TENANT_LOGIN, request.url));
  }

  // Subcontractor scope view is the one "distinct, minimal route tree" — no
  // one else lands there, and subcontractors land nowhere else.
  if (pathname.startsWith("/scope") && role !== "subcontractor") {
    return NextResponse.redirect(new URL(home, request.url));
  }
  if (role === "subcontractor" && !pathname.startsWith("/scope")) {
    return NextResponse.redirect(new URL(home, request.url));
  }
  // Change-review and team management are company_admin actions; employees
  // keep their (possibly view-only) dashboard access but not these.
  if ((pathname.startsWith("/review-queue") || pathname.startsWith("/team")) && role === "company_employee") {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
