// Edge middleware.
//
// Guest mode is ON by design: unauthenticated visitors may browse the catalog
// AND read books, with a small local trial of Q&A / notes. So nothing is
// redirected here. The real authorization boundary is FastAPI — admin and
// write endpoints require a session; guest Q&A streams but persists nothing.
//
// The matcher is intentionally empty; keep this file so re-enabling a gate later
// is a one-line change rather than a new file.
import { NextResponse } from "next/server";

export function middleware() {
  return NextResponse.next();
}

export const config = {
  matcher: [],
};
