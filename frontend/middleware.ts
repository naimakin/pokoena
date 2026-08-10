import { NextRequest, NextResponse } from "next/server";

// This cookie carries no authority — it only lets the edge middleware route by
// role without verifying a JWT. Every API call re-derives the role server-side
// from the signed, httpOnly session cookie.
const ROLE_COOKIE = "poko_role";

const ROLE_HOME: Record<string, string> = {
  admin: "/dashboard",
  viewer: "/dashboard",
  subcontractor: "/scope",
};

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const role = request.cookies.get(ROLE_COOKIE)?.value;
  const home = role ? (ROLE_HOME[role] ?? "/login") : "/login";

  if (pathname === "/") {
    return NextResponse.redirect(new URL(home, request.url));
  }

  if (pathname === "/login") {
    if (role) {
      return NextResponse.redirect(new URL(home, request.url));
    }
    return NextResponse.next();
  }

  if (!role) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if (pathname.startsWith("/scope") && role !== "subcontractor") {
    return NextResponse.redirect(new URL(home, request.url));
  }

  if ((pathname.startsWith("/dashboard") || pathname.startsWith("/review-queue")) && role === "subcontractor") {
    return NextResponse.redirect(new URL(home, request.url));
  }

  if (pathname.startsWith("/review-queue") && role === "viewer") {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
