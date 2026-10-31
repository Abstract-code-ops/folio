// Next.js API route handler — proxies requests to the FastAPI backend.
// This avoids CORS and DNS issues since the browser talks to Next.js
// (same origin) while Next.js forwards to the API inside the Docker network.

import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

const API_BASE = process.env.API_URL ?? "http://api:8000";

// Resolve the Authorization header for the upstream API.
//
// Preferred source is the HttpOnly Better Auth session cookie: the proxy runs
// on the server, reads the session via Better Auth, and forwards the session
// `token` as a Bearer header. The token is never exposed to browser JS.
//
// An explicit incoming Authorization header wins (useful for tests/tools).
// If the auth tables do not exist yet or the DB is unreachable, we fall through
// to no auth rather than failing the request.
async function resolveAuthorization(request: NextRequest): Promise<string | null> {
  const existing = request.headers.get("authorization");
  if (existing) return existing;
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    const token = session?.session?.token;
    return token ? `Bearer ${token}` : null;
  } catch {
    return null;
  }
}

// Headers worth carrying back to the browser so repeat navigations can be
// served from its cache (and revalidated) instead of hitting the API again.
const CACHE_HEADERS = ["cache-control", "etag", "last-modified", "vary"];

function copyCacheHeaders(from: Headers, to: Headers): void {
  for (const name of CACHE_HEADERS) {
    const value = from.get(name);
    if (value) to.set(name, value);
  }
}

const BODYLESS = new Set(["GET", "DELETE"]);

async function forward(
  request: NextRequest,
  path: string[],
  method: string,
): Promise<NextResponse> {
  const pathname = "/" + path.join("/");
  const queryString = request.nextUrl.search;
  const url = `${API_BASE}${pathname}${queryString}`;
  const authorization = await resolveAuthorization(request);

  // Forward conditional-request headers so a cached copy can 304.
  const conditional: Record<string, string> = {};
  const ifNoneMatch = request.headers.get("if-none-match");
  if (ifNoneMatch) conditional["if-none-match"] = ifNoneMatch;
  const ifModifiedSince = request.headers.get("if-modified-since");
  if (ifModifiedSince) conditional["if-modified-since"] = ifModifiedSince;

  try {
    const res = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(authorization ? { authorization } : {}),
        ...conditional,
      },
      body: BODYLESS.has(method) ? undefined : await request.text(),
    });

    const contentType = res.headers.get("content-type") ?? "";

    // Streaming response (NDJSON from Q&A, chapter-range and topic generation)
    if (contentType.includes("x-ndjson") || contentType.includes("stream")) {
      const { readable, writable } = new TransformStream();
      res.body?.pipeTo(writable);
      const headers = new Headers({
        "Content-Type": contentType,
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
      });
      return new NextResponse(readable, { status: res.status, headers });
    }

    // 204 and 304 must not carry a body, and an empty string breaks them.
    if (res.status === 204 || res.status === 304) {
      const headers = new Headers();
      copyCacheHeaders(res.headers, headers);
      return new NextResponse(null, { status: res.status, headers });
    }

    const body = await res.text();
    const headers = new Headers({
      "Content-Type": contentType || "application/json",
    });
    copyCacheHeaders(res.headers, headers);
    return new NextResponse(body, { status: res.status, headers });
  } catch (err) {
    console.error(`Proxy ${method} ${pathname} failed:`, err);
    return NextResponse.json(
      { error: `Failed to proxy request to ${pathname}` },
      { status: 502 },
    );
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return forward(request, path, "GET");
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return forward(request, path, "POST");
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return forward(request, path, "PUT");
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return forward(request, path, "DELETE");
}
