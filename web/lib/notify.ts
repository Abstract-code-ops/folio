// Subtle, non-obstructive notifications (sonner toasts).
//
// `notifyUnauthorized` is used when a guest hits an endpoint that needs an
// account — it's debounced so it never spams, and offers a Sign-in action that
// redirects. `notifyNoteReady` is the minimal "a note finished" confirmation.

import { toast } from "sonner";

let lastUnauthorizedAt = 0;

/** Tell a guest they need an account, with a one-tap redirect to sign-in. */
export function notifyUnauthorized(): void {
  const now = Date.now();
  if (now - lastUnauthorizedAt < 8000) return; // debounce repeats
  lastUnauthorizedAt = now;

  toast("Sign in to save this to your account", {
    description:
      "As a guest, what you create stays on this device only. An account keeps it everywhere.",
    duration: 7000,
    action: {
      label: "Sign in",
      onClick: () => {
        if (typeof window !== "undefined") {
          window.location.assign(
            `/sign-in?redirect=${encodeURIComponent(
              window.location.pathname + window.location.search,
            )}`,
          );
        }
      },
    },
  });
}

/** Minimal confirmation that a note finished generating/saving. */
export function notifyNoteReady(title?: string | null): void {
  toast.success(title ? `Note ready: ${title}` : "Note ready", {
    duration: 2200,
  });
}
