// Next.js API route — proxies PDFs from Supabase Storage for the EmbedPDF/PDFium viewer.
//
// Why it exists: the WASM PDF engine needs same-origin bytes with range support.
//
// Two delivery modes:
// - SMALL files: buffer the bytes and set an exact Content-Length. Streaming a
//   re-encoded body while copying upstream's Content-Length caused length
//   mismatches → the browser never saw the response complete (hangs) or got a
//   truncated file (PDFium "format error 3"). Buffering removes that class of bug.
// - LARGE files: stream them (no copied Content-Length, chunked). Buffering a
//   big PDF (tens–hundreds of MB) in the Node route stalls/kills the worker, so
//   we must not materialize it. Ranges are still relayed.
//
// Caching: full 200 → short cache (fast reopens); 206 partial → no-store (a
// cached partial poisons the viewer).

import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Above this, stream instead of buffering.
const BUFFER_LIMIT = 30 * 1024 * 1024; // 30 MB

function commonHeaders(upstream: Response): Headers {
  const headers = new Headers();
  headers.set(
    "content-type",
    upstream.headers.get("content-type") || "application/pdf",
  );
  headers.set("accept-ranges", "bytes");
  const contentRange = upstream.headers.get("content-range");
  if (contentRange) headers.set("content-range", contentRange);
  headers.set(
    "cache-control",
    upstream.status === 206 ? "no-store" : "public, max-age=3600",
  );
  return headers;
}

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");
  if (!url) return new NextResponse("Missing url", { status: 400 });

  const headers: Record<string, string> = {};
  const range = req.headers.get("range");
  if (range) headers.range = range;

  let upstream: Response;
  try {
    upstream = await fetch(url, { headers, redirect: "follow" });
  } catch {
    return new NextResponse("Upstream fetch failed", { status: 502 });
  }

  if (upstream.status !== 200 && upstream.status !== 206) {
    return new NextResponse(`Upstream ${upstream.status}`, { status: 502 });
  }

  const declared = Number(upstream.headers.get("content-length") ?? "0");

  // Large file (or range) — stream without materializing, no copied content-length.
  if (upstream.status === 206 || declared > BUFFER_LIMIT) {
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: commonHeaders(upstream),
    });
  }

  // Small full file — buffer for an exact Content-Length.
  const bytes = Buffer.from(await upstream.arrayBuffer());
  const out = commonHeaders(upstream);
  out.set("content-length", String(bytes.byteLength));
  return new NextResponse(bytes, { status: 200, headers: out });
}

export async function HEAD(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");
  if (!url) return new NextResponse("Missing url", { status: 400 });

  let upstream: Response;
  try {
    upstream = await fetch(url, { method: "HEAD", redirect: "follow" });
  } catch {
    return new NextResponse("Upstream fetch failed", { status: 502 });
  }
  if (!upstream.ok) {
    return new NextResponse(`Upstream ${upstream.status}`, { status: 502 });
  }

  const out = new Headers();
  out.set(
    "content-type",
    upstream.headers.get("content-type") || "application/pdf",
  );
  out.set("accept-ranges", "bytes");
  const cl = upstream.headers.get("content-length");
  if (cl) out.set("content-length", cl);
  out.set("cache-control", "public, max-age=3600");
  return new NextResponse(null, { status: 200, headers: out });
}
