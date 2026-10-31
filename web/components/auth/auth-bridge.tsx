"use client";

// Namespaces the local-first caches to the signed-in user.
//
// The persist storage is keyed by a remembered user id (`<name>:<userId>`), read
// synchronously at hydration. Account switches (sign-in / sign-out) re-namespace
// and reload from the sign-in page itself, so this component only has one job:
// on first load, if the active session and the stored namespace disagree (e.g.
// first visit with a live cookie, or a cookie changed in another tab), align
// them and reload once so the stores hydrate the right bucket.
//
// A reload is deliberate: it guarantees the in-memory zustand state matches the
// user's persisted bucket, with no fragile merge/clear step that could leak one
// account's notes into another's.

import { useEffect, useRef } from "react";
import { authClient } from "@/lib/auth-client";
import { getRememberedUserId, rememberUserId } from "@/lib/user-scope";

export function AuthBridge() {
  const { data, isPending } = authClient.useSession();
  const userId: string | null = data?.user?.id ?? null;
  const ran = useRef(false);

  useEffect(() => {
    if (isPending || ran.current) return;
    ran.current = true;

    if (getRememberedUserId() !== userId) {
      rememberUserId(userId);
      window.location.reload();
    }
  }, [isPending, userId]);

  return null;
}
