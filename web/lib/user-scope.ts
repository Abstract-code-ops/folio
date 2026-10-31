// Per-user localStorage namespacing for the local-first caches.
//
// Notes and chat are persisted with zustand `persist`. On a shared browser two
// accounts would read/write the same keys and see each other's data, so each
// store's storage is keyed by the currently remembered user id: `<name>:<uid>`.
// Each account keeps its OWN bucket across sign-out/sign-in — caching stays
// useful, it is just no longer shared.
//
// The remembered id is a small plaintext localStorage value. Better Auth's
// session cookie is HttpOnly (JS can't read it), so this is the synchronous id
// handle the persist storage needs at hydration time. It is only a cache
// namespace, never an authorization signal — the API verifies the real session.

import type { StateStorage } from "zustand/middleware";

const LAST_USER_KEY = "folio-auth-uid";
const ANON = "anon";

export function rememberUserId(id: string | null): void {
  if (typeof localStorage === "undefined") return;
  try {
    if (id) localStorage.setItem(LAST_USER_KEY, id);
    else localStorage.removeItem(LAST_USER_KEY);
  } catch {
    /* ignore quota / private-mode errors */
  }
}

/** The remembered user id (null when signed out / never set). */
export function getRememberedUserId(): string | null {
  if (typeof localStorage === "undefined") return null;
  try {
    return localStorage.getItem(LAST_USER_KEY);
  } catch {
    return null;
  }
}

function bucket(): string {
  if (typeof localStorage === "undefined") return ANON;
  try {
    return localStorage.getItem(LAST_USER_KEY) ?? ANON;
  } catch {
    return ANON;
  }
}

/** localStorage namespaced per user: real key becomes `<name>:<userId>`. */
export function userScopedStorage(): StateStorage {
  return {
    getItem: (name) => {
      if (typeof localStorage === "undefined") return null;
      return localStorage.getItem(`${name}:${bucket()}`);
    },
    setItem: (name, value) => {
      if (typeof localStorage === "undefined") return;
      localStorage.setItem(`${name}:${bucket()}`, value);
    },
    removeItem: (name) => {
      if (typeof localStorage === "undefined") return;
      localStorage.removeItem(`${name}:${bucket()}`);
    },
  };
}
