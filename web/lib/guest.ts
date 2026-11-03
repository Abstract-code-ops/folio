// Guest-mode limits + a synchronous auth flag.
//
// AuthBridge sets `setAuthed(...)` from the live session so non-hook code (store
// actions, event handlers) can tell a guest from a signed-in user without
// subscribing to the session hook.

export const GUEST_QA_LIMIT = 10;
export const GUEST_NOTES_LIMIT = 3;

let authed = false;

export function isAuthed(): boolean {
  return authed;
}

export function setAuthed(value: boolean): void {
  authed = value;
}
