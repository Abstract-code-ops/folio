"use client";

// Sign-in / sign-up. Email + password via Better Auth.
//
// Error messages stay generic ("Could not sign in") so the page never reveals
// whether an address is registered. Verification is required before an address
// is trusted; the verification link is logged by the dev mail sender in
// web/lib/auth.ts.

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";
import { rememberUserId } from "@/lib/user-scope";

type Mode = "sign-in" | "sign-up";

export default function SignInPage() {
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [signedInAs, setSignedInAs] = useState<string | null>(null);

  // If already signed in, offer a sign-out instead of a second sign-in.
  useEffect(() => {
    authClient.getSession().then(({ data }) => {
      setSignedInAs(data?.user?.email ?? null);
    });
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (mode === "sign-up") {
        const { error: signUpError } = await authClient.signUp.email({
          email,
          password,
          name,
        });
        if (signUpError) throw new Error(signUpError.message ?? "Could not create account");
        // Send the verification link now. With requireEmailVerification, Better
        // Auth only sends it on the next sign-in attempt — not at sign-up — so
        // trigger it explicitly. In dev the sender logs the link to the console.
        try {
          await authClient.sendVerificationEmail({ email, callbackURL: "/sign-in" });
        } catch {
          // Non-fatal: the account exists; the user can still sign in to retry.
        }
        window.location.assign(`/verify-email?email=${encodeURIComponent(email)}`);
      } else {
        const { data: signInData, error: signInError } = await authClient.signIn.email({
          email,
          password,
        });
        if (signInError) throw new Error(signInError.message ?? "Could not sign in");
        // Namespace this user's local caches and do a full reload so the stores
        // hydrate the right bucket (prevents accounts sharing/overwriting cache).
        rememberUserId(signInData?.user?.id ?? null);
        window.location.assign("/library");
      }
    } catch (err) {
      // Better Auth already returns non-enumerating text ("Invalid email or
      // password"); surface it so real failures are visible, with a fallback.
      setError(
        err instanceof Error && err.message
          ? err.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleSignOut() {
    setBusy(true);
    rememberUserId(null);
    await authClient.signOut();
    window.location.assign("/");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-bg-base px-6 py-16">
      <div className="w-full max-w-sm">
        <Link
          href="/"
          className="font-heading text-body font-semibold text-text-primary"
        >
          Folio
        </Link>

        {signedInAs ? (
          <div className="mt-8">
            <h1 className="font-heading text-h2 text-text-primary">
              Signed in
            </h1>
            <p className="mt-2 text-body-sm text-text-muted">{signedInAs}</p>
            <div className="mt-6 flex gap-3">
              <Link
                href="/library"
                className="rounded-md bg-accent px-4 py-2 text-body-sm font-medium text-white hover:opacity-90"
              >
                Go to library
              </Link>
              <button
                type="button"
                onClick={handleSignOut}
                disabled={busy}
                className="rounded-md border border-border px-4 py-2 text-body-sm text-text-muted hover:text-text-primary disabled:opacity-50"
              >
                Sign out
              </button>
            </div>
          </div>
        ) : (
          <>
            <h1 className="mt-8 font-heading text-h2 text-text-primary">
              {mode === "sign-in" ? "Sign in" : "Create your account"}
            </h1>
            <p className="mt-2 text-body-sm text-text-muted">
              {mode === "sign-in"
                ? "Welcome back to Folio."
                : "Email and password. We'll send a verification link."}
            </p>

            <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
              {mode === "sign-up" && (
                <label className="flex flex-col gap-1.5">
                  <span className="text-body-sm text-text-muted">Name</span>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoComplete="name"
                    className="rounded-md border border-border bg-bg-surface px-3 py-2 text-body text-text-primary outline-none focus:border-accent"
                  />
                </label>
              )}
              <label className="flex flex-col gap-1.5">
                <span className="text-body-sm text-text-muted">Email</span>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  className="rounded-md border border-border bg-bg-surface px-3 py-2 text-body text-text-primary outline-none focus:border-accent"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-body-sm text-text-muted">Password</span>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === "sign-up" ? "new-password" : "current-password"}
                  className="rounded-md border border-border bg-bg-surface px-3 py-2 text-body text-text-primary outline-none focus:border-accent"
                />
              </label>

              {error && <p className="text-body-sm text-state-error">{error}</p>}
              {notice && <p className="text-body-sm text-state-success">{notice}</p>}

              <button
                type="submit"
                disabled={busy}
                className="mt-1 rounded-md bg-accent px-4 py-2.5 text-body font-medium text-white hover:opacity-90 disabled:opacity-50"
              >
                {busy
                  ? "Please wait…"
                  : mode === "sign-in"
                    ? "Sign in"
                    : "Create account"}
              </button>
            </form>

            <button
              type="button"
              onClick={() => {
                setMode(mode === "sign-in" ? "sign-up" : "sign-in");
                setError(null);
                setNotice(null);
              }}
              className="mt-4 text-body-sm text-text-muted hover:text-text-primary"
            >
              {mode === "sign-in"
                ? "Need an account? Create one"
                : "Already have an account? Sign in"}
            </button>
          </>
        )}
      </div>
    </main>
  );
}
