// Generates the bumpy, gyri-like outer silhouette of the brain from the
// exact control points of the original (smooth) outline, so the overall
// proportions never change — only the boundary gets a rounded "bump" pass.
// Every knob that affects the shape lives in config.ts (BRAIN_SHAPE).

export interface Point {
  x: number;
  y: number;
}

export interface BrainShapeConfig {
  bumpCount: number;
  bumpDepth: number;
  secondaryWaveMix: number;
  samplesPerSegment: number;
}

// A tiny deterministic PRNG (no external dependency). The same seed always
// produces the same sequence, so layouts stay stable across renders/reloads.
export function mulberry32(seed: number): () => number {
  let a = seed;
  return function random() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Exact control points of the original hand-drawn outline (unchanged), so
// the bumpy version keeps the same footprint and proportions.
const OUTLINE_START: Point = { x: 150, y: 40 };
const OUTLINE_SEGMENTS: Array<[number, number, number, number, number, number]> = [
  [180, 35, 220, 35, 250, 40],
  [280, 45, 310, 55, 330, 75],
  [350, 95, 365, 125, 370, 160],
  [375, 195, 370, 230, 355, 260],
  [340, 290, 315, 310, 280, 325],
  [245, 340, 210, 345, 200, 350],
  [190, 355, 180, 360, 170, 355],
  [160, 350, 155, 340, 150, 335],
  [145, 340, 140, 350, 130, 355],
  [120, 360, 110, 355, 100, 350],
  [90, 345, 55, 340, 20, 325],
  [-15, 310, -40, 290, -55, 260],
  [-70, 230, -75, 195, -70, 160],
  [-65, 125, -50, 95, -30, 75],
  [-10, 55, 20, 45, 50, 40],
  [80, 35, 120, 35, 150, 40],
];

// The interior sulcus curve — kept exactly as the original, unbumped,
// since only the outer circumference should read as gyri-like.
export const BRAIN_SULCUS_PATH =
  "M 150 40 C 148 80, 145 140, 145 200 C 145 260, 148 320, 150 335";

function cubicBezierPoint(p0: Point, cp1: Point, cp2: Point, p3: Point, t: number): Point {
  const mt = 1 - t;
  const a = mt * mt * mt;
  const b = 3 * mt * mt * t;
  const c = 3 * mt * t * t;
  const d = t * t * t;
  return {
    x: a * p0.x + b * cp1.x + c * cp2.x + d * p3.x,
    y: a * p0.y + b * cp1.y + c * cp2.y + d * p3.y,
  };
}

function sampleOutline(samplesPerSegment: number): Point[] {
  const points: Point[] = [];
  let start = OUTLINE_START;
  for (const [c1x, c1y, c2x, c2y, ex, ey] of OUTLINE_SEGMENTS) {
    const cp1 = { x: c1x, y: c1y };
    const cp2 = { x: c2x, y: c2y };
    const end = { x: ex, y: ey };
    for (let i = 0; i < samplesPerSegment; i++) {
      points.push(cubicBezierPoint(start, cp1, cp2, end, i / samplesPerSegment));
    }
    start = end;
  }
  return points;
}

export function getPolygonCentroid(points: Point[]): Point {
  const n = points.length || 1;
  const sum = points.reduce((acc, p) => ({ x: acc.x + p.x, y: acc.y + p.y }), { x: 0, y: 0 });
  return { x: sum.x / n, y: sum.y / n };
}

// Pushes every sampled point outward/inward along a sine-wave pattern to
// create rounded, gyri-like bumps around the perimeter, radiating from the
// shape's own centroid (robust for any roughly-convex blob like this one).
export function getBumpyBrainOutlinePoints(cfg: BrainShapeConfig): Point[] {
  const raw = sampleOutline(cfg.samplesPerSegment);
  const centroid = getPolygonCentroid(raw);
  const n = raw.length;

  return raw.map((p, i) => {
    const s = i / n;
    const theta = s * Math.PI * 2;
    const bump =
      Math.sin(theta * cfg.bumpCount) * cfg.bumpDepth +
      Math.sin(theta * cfg.bumpCount * 2.3 + 1.7) * cfg.bumpDepth * cfg.secondaryWaveMix;
    const dx = p.x - centroid.x;
    const dy = p.y - centroid.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    return {
      x: p.x + (dx / dist) * bump,
      y: p.y + (dy / dist) * bump,
    };
  });
}

// Uniform Catmull-Rom -> cubic Bezier conversion for a closed loop, so the
// bumps read as smooth, rounded lobes rather than sharp zig-zags.
export function smoothClosedPathFromPoints(points: Point[]): string {
  const n = points.length;
  if (n < 3) return "";
  let d = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)} `;
  for (let i = 0; i < n; i++) {
    const p0 = points[(i - 1 + n) % n];
    const p1 = points[i];
    const p2 = points[(i + 1) % n];
    const p3 = points[(i + 2) % n];
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    d += `C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)} `;
  }
  return d + "Z";
}

export function getBumpyBrainOutlinePath(cfg: BrainShapeConfig): string {
  return smoothClosedPathFromPoints(getBumpyBrainOutlinePoints(cfg));
}

// Standard ray-casting point-in-polygon test, used to keep the ambient
// background dots confined inside the brain silhouette.
export function pointInPolygon(x: number, y: number, poly: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x;
    const yi = poly[i].y;
    const xj = poly[j].x;
    const yj = poly[j].y;
    const intersect = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}
