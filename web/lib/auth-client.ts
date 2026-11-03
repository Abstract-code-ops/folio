// Browser-side Better Auth client.
//
// The session is resolved server-side — the Next proxy route reads the HttpOnly
// Better Auth session cookie via `auth.api.getSession` and forwards the token to
// FastAPI as a Bearer header (see web/app/api/proxy/[...path]/route.ts). Browser
// JS never sees the token, so this module only exposes the client for the
// sign-in / sign-out UI.

import { createAuthClient } from "better-auth/react";

export const authClient = createAuthClient({
  baseURL: process.env.NEXT_PUBLIC_BETTER_AUTH_URL || undefined,
});
