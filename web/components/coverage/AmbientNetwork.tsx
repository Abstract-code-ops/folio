"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { AMBIENT_NETWORK } from "./config";
import { mulberry32, pointInPolygon, getPolygonCentroid } from "./brainShape";
import type { Point } from "./brainShape";

interface AmbientNetworkProps {
  viewBox: { minX: number; minY: number; width: number; height: number };
  outlinePoints: Point[];
  className?: string;
}

interface Edge {
  a: number;
  b: number;
}

interface Pulse {
  edge: Edge;
  start: number;
  duration: number;
}

// Purely decorative neural-network texture behind the real coverage nodes.
// It is never bound to book data — it just gives the brain a sense of
// quiet, constant background activity. Safe to delete or restyle without
// touching any coverage logic in BrainMap.tsx.
export function AmbientNetwork({ viewBox, outlinePoints, className }: AmbientNetworkProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvasEl = canvasRef.current;
    if (!canvasEl || outlinePoints.length < 3) return;
    const ctx2d = canvasEl.getContext("2d");
    if (!ctx2d) return;
    // Re-bind to explicitly non-nullable consts: TS does not carry the
    // above narrowing into the nested closures below (resize/draw/toCanvas),
    // since it can't prove they only run after this check.
    const canvas: HTMLCanvasElement = canvasEl;
    const ctx: CanvasRenderingContext2D = ctx2d;

    const prefersReducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Confine ambient dots just inside the bumpy silhouette.
    const centroid = getPolygonCentroid(outlinePoints);
    const insetPolygon = outlinePoints.map((p) => ({
      x: centroid.x + (p.x - centroid.x) * AMBIENT_NETWORK.insetMargin,
      y: centroid.y + (p.y - centroid.y) * AMBIENT_NETWORK.insetMargin,
    }));

    const rand = mulberry32(AMBIENT_NETWORK.seed);
    const dots: Point[] = [];
    let attempts = 0;
    const maxAttempts = AMBIENT_NETWORK.dotCount * 60;
    while (dots.length < AMBIENT_NETWORK.dotCount && attempts < maxAttempts) {
      attempts++;
      const x = viewBox.minX + rand() * viewBox.width;
      const y = viewBox.minY + rand() * viewBox.height;
      if (pointInPolygon(x, y, insetPolygon)) dots.push({ x, y });
    }

    // Connect each dot to its nearest few neighbors only, so the network
    // reads as a constellation rather than an all-to-all tangle.
    const edges: Edge[] = [];
    const seenEdges = new Set<string>();
    dots.forEach((d, i) => {
      const nearest = dots
        .map((o, j) => ({ j, dist: Math.hypot(d.x - o.x, d.y - o.y) }))
        .filter((o) => o.j !== i && o.dist < AMBIENT_NETWORK.maxLinkDistance)
        .sort((p, q) => p.dist - q.dist)
        .slice(0, AMBIENT_NETWORK.neighborsPerDot);
      nearest.forEach(({ j }) => {
        const key = i < j ? `${i}:${j}` : `${j}:${i}`;
        if (!seenEdges.has(key)) {
          seenEdges.add(key);
          edges.push({ a: i, b: j });
        }
      });
    });

    let pulses: Pulse[] = [];
    let lastSpawn = 0;
    let rafId = 0;
    let scaleX = 1;
    let scaleY = 1;

    function resize() {
      const parent = canvas.parentElement;
      if (!parent) return;
      const dpr = window.devicePixelRatio || 1;
      const w = parent.clientWidth;
      const h = parent.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      scaleX = w / viewBox.width;
      scaleY = h / viewBox.height;
    }

    function toCanvas(p: Point) {
      return { x: (p.x - viewBox.minX) * scaleX, y: (p.y - viewBox.minY) * scaleY };
    }

    function draw(time: number) {
      const parent = canvas.parentElement;
      if (!parent) return;
      ctx.clearRect(0, 0, parent.clientWidth, parent.clientHeight);

      ctx.strokeStyle = AMBIENT_NETWORK.lineColor;
      ctx.lineWidth = 0.6;
      edges.forEach((e) => {
        const a = toCanvas(dots[e.a]);
        const b = toCanvas(dots[e.b]);
        ctx.globalAlpha = AMBIENT_NETWORK.lineOpacity;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      });

      ctx.fillStyle = AMBIENT_NETWORK.dotColor;
      dots.forEach((d) => {
        const p = toCanvas(d);
        ctx.globalAlpha = AMBIENT_NETWORK.dotOpacity;
        ctx.beginPath();
        ctx.arc(p.x, p.y, AMBIENT_NETWORK.dotRadius, 0, Math.PI * 2);
        ctx.fill();
      });

      if (!prefersReducedMotion && edges.length > 0) {
        if (
          time - lastSpawn > AMBIENT_NETWORK.pulse.spawnIntervalMs &&
          pulses.length < AMBIENT_NETWORK.pulse.maxConcurrent
        ) {
          lastSpawn = time;
          const edge = edges[Math.floor(rand() * edges.length)];
          pulses.push({
            edge,
            start: time,
            duration: AMBIENT_NETWORK.pulse.durationMs * (0.7 + rand() * 0.6),
          });
        }
        pulses = pulses.filter((p) => time - p.start < p.duration);

        ctx.fillStyle = AMBIENT_NETWORK.pulse.color;
        pulses.forEach((p) => {
          const progress = Math.min(1, Math.max(0, (time - p.start) / p.duration));
          const a = toCanvas(dots[p.edge.a]);
          const b = toCanvas(dots[p.edge.b]);
          const x = a.x + (b.x - a.x) * progress;
          const y = a.y + (b.y - a.y) * progress;
          ctx.globalAlpha = Math.sin(progress * Math.PI);
          ctx.beginPath();
          ctx.arc(x, y, AMBIENT_NETWORK.pulse.radius, 0, Math.PI * 2);
          ctx.fill();
        });
      }

      ctx.globalAlpha = 1;
      rafId = requestAnimationFrame(draw);
    }

    resize();
    rafId = requestAnimationFrame(draw);

    const resizeObserver = new ResizeObserver(resize);
    if (canvas.parentElement) resizeObserver.observe(canvas.parentElement);

    return () => {
      cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
    };
  }, [viewBox, outlinePoints]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={cn("absolute inset-0 pointer-events-none", className)}
    />
  );
}
