"use client";

// Auth-aware nav item: a "Sign in" link when signed out, and when signed in a
// circular avatar that opens a small dropdown with the account email and a
// Sign-out action. Signing out re-namespaces the local caches and reloads so the
// next account never inherits this one's data.

import { useState } from "react";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";
import { rememberUserId } from "@/lib/user-scope";
import { landing } from "@/content/landing";

export function AuthNav() {
  const { data, isPending } = authClient.useSession();
  const [open, setOpen] = useState(false);

  if (isPending) {
    return <span className="h-8 w-8 rounded-full bg-bg-elevated" aria-hidden />;
  }

  if (!data?.user) {
    return (
      <Link
        href="/sign-in"
        className="font-heading text-body-sm text-text-muted hover:text-text-primary transition-colors"
      >
        {landing.nav.signIn}
      </Link>
    );
  }

  const label = data.user.name || data.user.email || "?";
  const initial = label.trim().charAt(0).toUpperCase();

  async function signOut() {
    rememberUserId(null);
    await authClient.signOut();
    window.location.assign("/");
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-body-sm font-semibold text-white hover:opacity-90"
      >
        {initial}
      </button>

      {open && (
        <>
          <button
            type="button"
            aria-hidden
            tabIndex={-1}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-40 cursor-default"
          />
          <div
            role="menu"
            className="absolute right-0 z-50 mt-2 w-52 rounded-md border border-border bg-bg-surface p-1 shadow-lg"
          >
            <div className="truncate px-3 py-2 text-body-sm text-text-muted">
              {data.user.email}
            </div>
            <button
              type="button"
              role="menuitem"
              onClick={signOut}
              className="w-full rounded px-3 py-2 text-left text-body-sm text-text-primary hover:bg-bg-elevated"
            >
              Sign out
            </button>
          </div>
        </>
      )}
    </div>
  );
}
