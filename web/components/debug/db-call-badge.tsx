"use client";

import { useEffect, useState } from "react";
import { getRequestCount, resetRequestCount } from "@/lib/request-counter";

/**
 * TEMPORARY debug badge — shows the session's DB-call count on screen so it can
 * be watched from a phone (no console). Tap to reset before a scenario.
 *
 * To remove: delete this file and the two references in `app/layout.tsx`
 * (the import and the `<DbCallBadge />`).
 */
export function DbCallBadge() {
  const [calls, setCalls] = useState(0);

  useEffect(() => {
    const tick = () => setCalls(getRequestCount());
    tick();
    const id = setInterval(tick, 500);
    return () => clearInterval(id);
  }, []);

  return (
    <button
      type="button"
      onClick={() => {
        resetRequestCount();
        setCalls(0);
      }}
      title="DB calls this session — tap to reset"
      aria-label={`${calls} database calls this session. Tap to reset.`}
      className="fixed bottom-3 left-3 z-[9999] rounded-full bg-black/80 px-3 py-1 font-mono text-xs text-lime-300 shadow-lg ring-1 ring-white/10"
    >
      DB {calls}
    </button>
  );
}
