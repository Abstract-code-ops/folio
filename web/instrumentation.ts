// Sentry — server & edge initialization (Next.js instrumentation hook).
//
// Sentry is imported *lazily* inside register() rather than at module top so
// its server SDK is not pulled into the per-request / prerender module graph.
// On some @sentry/nextjs versions a top-level import leaks next/document's
// <Html> into the app-router 404 render, which fails the production build with
// "<Html> should not be imported outside of pages/_document".
export async function register() {
  const dsn = process.env.SENTRY_DSN ?? process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;

  const runtime = process.env.NEXT_RUNTIME;
  if (runtime !== "nodejs" && runtime !== "edge") return;

  try {
    const Sentry = await import("@sentry/nextjs");
    Sentry.init({
      dsn,
      tracesSampleRate: 0.1,
      environment: process.env.NODE_ENV,
    });
  } catch {
    // never let observability break boot
  }
}
