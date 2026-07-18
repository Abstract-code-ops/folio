// Next.js API route — proxies PDF files from Supabase Storage.
// Forwards Range headers for pdf.js byte-range requests so the browser
// downloads only the chunks it needs instead of the full file.
// Usage: /api/pdf?url=https://supabase.co/storage/.../file.pdf

import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");
  if (!url) return new NextResponse("Missing url", { status: 400 });

  const range = req.headers.get("range");
  const upstream = await fetch(url, {
    headers: range ? { Range: range } : {},
  });

  if (!upstream.ok && upstream.status !== 206) {
    return new NextResponse(upstream.statusText, { status: upstream.status });
  }

  const headers = new Headers({
    "Content-Type": "application/pdf",
    "Accept-Ranges": "bytes",
    "Cache-Control": "public, max-age=31536000, immutable",
  });
  const contentRange = upstream.headers.get("content-range");
  if (contentRange) headers.set("Content-Range", contentRange);
  const contentLength = upstream.headers.get("content-length");
  if (contentLength) headers.set("Content-Length", contentLength);

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers,
  });
}

export async function HEAD(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");
  if (!url) return new NextResponse("Missing url", { status: 400 });

  const upstream = await fetch(url, { method: "HEAD" });
  if (!upstream.ok) {
    return new NextResponse(upstream.statusText, { status: upstream.status });
  }

  const headers = new Headers({
    "Content-Type": "application/pdf",
    "Accept-Ranges": "bytes",
    "Cache-Control": "public, max-age=31536000, immutable",
  });
  const contentLength = upstream.headers.get("content-length");
  if (contentLength) headers.set("Content-Length", contentLength);

  return new NextResponse(null, { status: 200, headers });
}