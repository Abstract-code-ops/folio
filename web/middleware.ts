// Edge middleware — UX gating only, NOT the authorization boundary.
//
// This redirects visitors without a session cookie away from the reader and
// library so they land on /sign-in instead of a broken page. It is deliberately
// defense-in-depth: the real security boundary is FastAPI, which verifies the
// session and ownership on every request. A page must never return sensitive
// data merely because this middleware let the request through.
//
// It is dormant unless NEXT_PUBLIC_AUTH_ENABLED=true, so wiring auth does not
// lock anyone out before the Better Auth schema and sign-in flow are live.

import { NextRequest, NextResponse } from "next/server";

const AUTH_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";

// Better Auth's session cookie (secure-prefixed in https deployments).
const SESSION_COOKIES = [
  "better-auth.session_token",
  "__Secure-better-auth.session_token",
];

function hasSessionCookie(request: NextRequest): boolean {
  return SESSION_COOKIES.some((name) => request.cookies.has(name));
}

export function middleware(request: NextRequest) {
  if (!AUTH_ENABLED) return NextResponse.next();
  if (hasSessionCookie(request)) return NextResponse.next();

  const url = request.nextUrl.clone();
  url.pathname = "/sign-in";
  url.search = `?redirect=${encodeURIComponent(
    request.nextUrl.pathname + request.nextUrl.search,
  )}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/library/:path*", "/reader/:path*"],
};
