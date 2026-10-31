// Browser-side Better Auth client + session-token helper.
//
// `getSessionToken()` is what the typed API client uses to build the
// `Authorization: Bearer <token>` header. The token is Better Auth's session
// `token` (not the row id) — the same column api/app/core/auth.py looks up.

import { createAuthClient } from "better-auth/react";

export const authClient = createAuthClient({
  baseURL: process.env.NEXT_PUBLIC_BETTER_AUTH_URL || undefined,
});

let cachedToken: string | null = null;

/** Fetch the current session token, or null when signed out. */
export async function getSessionToken(force = false): Promise<string | null> {
  if (cachedToken && !force) return cachedToken;
  const { data } = await authClient.getSession();
  cachedToken = data?.session?.token ?? null;
  return cachedToken;
}

/** Drop the cached token (call on sign-in/sign-out). */
export function clearSessionTokenCache(): void {
  cachedToken = null;
}
