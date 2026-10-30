/**
 * Dev-only DB-call counter.
 *
 * Every backend request the app makes goes through the same-origin `/api/proxy`
 * route, so counting requests whose URL contains `/api/proxy` gives a faithful
 * count of DB round trips during a session. Installed once (from api-client on
 * the client); a no-op on the server and in tests.
 *
 * Inspect live in the console: `window.__folioDbCalls` (number) and
 * `window.__folioReset()`.
 */

let calls = 0;
let installed = false;

export function getRequestCount(): number {
  return calls;
}

export function resetRequestCount(): void {
  calls = 0;
  publish();
}

function publish(): void {
  if (typeof window === "undefined") return;
  const w = window as unknown as {
    __folioDbCalls?: number;
    __folioReset?: () => void;
  };
  w.__folioDbCalls = calls;
  w.__folioReset = resetRequestCount;
}

export function installRequestCounter(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;

  const original = window.fetch.bind(window);
  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.href
          : (input as Request).url;
    if (url.includes("/api/proxy")) {
      calls += 1;
      publish();
      if (process.env.NODE_ENV !== "production") {
        // eslint-disable-next-line no-console
        console.debug(`[folio] DB call #${calls} ${init?.method ?? "GET"} ${url}`);
      }
    }
    return original(input as RequestInfo, init);
  }) as typeof fetch;

  publish();
}
