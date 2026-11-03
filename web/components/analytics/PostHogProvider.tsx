"use client";

// PostHog analytics — client-side init + manual pageview capture.
// Keys come from NEXT_PUBLIC_POSTHOG_KEY / NEXT_PUBLIC_POSTHOG_HOST (.env).
// init() is guarded so it runs once even under React Strict Mode double-mounts.

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import posthog from "posthog-js";
import { PostHogProvider as PHProvider } from "posthog-js/react";

let initialized = false;

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  useEffect(() => {
    if (initialized) return;
    const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
    if (!key) return;
    posthog.init(key, {
      api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://eu.i.posthog.com",
      capture_pageview: false, // captured manually on route change below
      autocapture: true, // clicks / interactions / user flows
      person_profiles: "identified_only",
    });
    initialized = true;
  }, []);

  useEffect(() => {
    if (!initialized || !pathname) return;
    posthog.capture("$pageview", { $current_url: window.origin + pathname });
  }, [pathname]);

  return <PHProvider client={posthog}>{children}</PHProvider>;
}
