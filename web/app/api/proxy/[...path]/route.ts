// Next.js API route handler — proxies requests to the FastAPI backend.
// This avoids CORS and DNS issues since the browser talks to Next.js
// (same origin) while Next.js forwards to the API inside the Docker network.

import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.API_URL ?? "http://api:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const pathname = "/" + path.join("/");
  const queryString = request.nextUrl.search;
  const url = `${API_BASE}${pathname}${queryString}`;

  try {
    const res = await fetch(url, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        // Forward auth header from the client if present
        ...(request.headers.get("authorization")
          ? { authorization: request.headers.get("authorization")! }
          : {}),
      },
    });

    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (err) {
    console.error(`Proxy GET ${pathname} failed:`, err);
    return NextResponse.json(
      { error: `Failed to proxy request to ${pathname}` },
      { status: 502 },
    );
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const pathname = "/" + path.join("/");
  const queryString = request.nextUrl.search;
  const url = `${API_BASE}${pathname}${queryString}`;

  try {
    const body = await request.text();
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(request.headers.get("authorization")
          ? { authorization: request.headers.get("authorization")! }
          : {}),
      },
      body,
    });

    const contentType = res.headers.get("content-type") ?? "";

    // Streaming response (NDJSON from Q&A or note generation)
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

    const responseBody = await res.text();
    return new NextResponse(responseBody, {
      status: res.status,
      headers: {
        "Content-Type": contentType || "application/json",
      },
    });
  } catch (err) {
    console.error(`Proxy POST ${pathname} failed:`, err);
    return NextResponse.json(
      { error: `Failed to proxy request to ${pathname}` },
      { status: 502 },
    );
  }
}