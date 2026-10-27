// Next.js API route handler — proxies requests to the FastAPI backend.
// This avoids CORS and DNS issues since the browser talks to Next.js
// (same origin) while Next.js forwards to the API inside the Docker network.

import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.API_URL ?? "http://api:8000";

// Every method funnels through one forwarder. The only real differences are
// whether a body is sent and whether the reply streams, and both are derived
// from the request/response rather than from the method name -- which is why a
// new verb is four lines instead of a copy of the fetch logic.

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

// Note autosave.
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

const BODYLESS = new Set(["GET", "DELETE"]);

async function forward(
  request: NextRequest,
  path: string[],
  method: string,
): Promise<NextResponse> {
  const pathname = "/" + path.join("/");
  const queryString = request.nextUrl.search;
  const url = `${API_BASE}${pathname}${queryString}`;
  const authorization = request.headers.get("authorization");

  try {
    const res = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        // Forward auth header from the client if present
        ...(authorization ? { authorization } : {}),
      },
      body: BODYLESS.has(method) ? undefined : await request.text(),
    });

    const contentType = res.headers.get("content-type") ?? "";

    // Streaming response (NDJSON from Q&A, chapter-range and topic generation)
    if (contentType.includes("x-ndjson") || contentType.includes("stream")) {
      const { readable, writable } = new TransformStream();
      res.body?.pipeTo(writable);
      return new NextResponse(readable, {
        status: res.status,
        headers: {
          "Content-Type": contentType,
          "Cache-Control": "no-cache",
          "X-Accel-Buffering": "no",
        },
      });
    }

    // 204 and 304 must not carry a body, and an empty string breaks them.
    if (res.status === 204 || res.status === 304) {
      return new NextResponse(null, { status: res.status });
    }

    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: {
        "Content-Type": contentType || "application/json",
      },
    });
  } catch (err) {
    console.error(`Proxy ${method} ${pathname} failed:`, err);
    return NextResponse.json(
      { error: `Failed to proxy request to ${pathname}` },
      { status: 502 },
    );
  }
}