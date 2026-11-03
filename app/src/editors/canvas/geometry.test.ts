// Plain assertions, no test runner: run with scratch/run-geometry-test.mjs (vite ssrLoadModule).
import {
  boundsOf, boxFromCorners, clientToPage, fitInside, fitWidthScale, fromVisual, imageWidthFor, moveBox,
  normalizeRotation, PX_PER_PT, remapPoint, resizeBox, scaleToZoom, stepZoom, toRect, toVisual, visualSize, zoomToScale,
} from "./geometry";
import type { Pt } from "./geometry";

function near(actual: number, expected: number, label: string): void {
  if (Math.abs(actual - expected) > 1e-6) throw new Error(`${label}: got ${actual}, wanted ${expected}`);
}

function samePt(actual: Pt, expected: Pt, label: string): void {
  near(actual.x, expected.x, `${label}.x`);
  near(actual.y, expected.y, `${label}.y`);
}

const RAW = { w: 600, h: 800 };
const tests: Array<[string, () => void]> = [];
const test = (name: string, fn: () => void) => tests.push([name, fn]);

test("rotation is normalised", () => {
  near(normalizeRotation(-90), 270, "-90");
  near(normalizeRotation(450), 90, "450");
  near(normalizeRotation(0), 0, "0");
});

test("visual size swaps for quarter turns", () => {
  near(visualSize(RAW, 90).w, 800, "90 w");
  near(visualSize(RAW, 270).h, 600, "270 h");
  near(visualSize(RAW, 180).w, 600, "180 w");
});

test("rotation maps corners like a clockwise page turn", () => {
  samePt(toVisual({ x: 0, y: 0 }, RAW, 90), { x: 800, y: 0 }, "90 origin goes top right");
  samePt(toVisual({ x: 0, y: 0 }, RAW, 180), { x: 600, y: 800 }, "180 origin goes bottom right");
  samePt(toVisual({ x: 0, y: 0 }, RAW, 270), { x: 0, y: 600 }, "270 origin goes bottom left");
});

test("toVisual and fromVisual are inverses for every rotation", () => {
  for (const rotation of [0, 90, 180, 270]) {
    const p = { x: 123.5, y: 456.25 };
    samePt(fromVisual(toVisual(p, RAW, rotation), RAW, rotation), p, `round trip ${rotation}`);
  }
});

test("rotated corners stay inside the visual page", () => {
  for (const rotation of [90, 180, 270]) {
    const size = visualSize(RAW, rotation);
    const corner = toVisual({ x: RAW.w, y: RAW.h }, RAW, rotation);
    if (corner.x < -1e-9 || corner.y < -1e-9 || corner.x > size.w + 1e-9 || corner.y > size.h + 1e-9) {
      throw new Error(`corner outside at ${rotation}`);
    }
  }
});

test("client pixels convert to points at any zoom and back", () => {
  for (const zoom of [0.25, 0.5, 1, 1.75, 4]) {
    const scale = zoomToScale(zoom);
    const origin = { left: 140.5, top: 60.25 };
    const pt = clientToPage({ x: origin.left + 200 * scale, y: origin.top + 300 * scale }, origin, scale);
    samePt(pt, { x: 200, y: 300 }, `zoom ${zoom}`);
  }
});

test("zoom and scale convert both ways", () => {
  near(zoomToScale(1), PX_PER_PT, "100%");
  near(scaleToZoom(zoomToScale(1.5)), 1.5, "150%");
});

test("fit width fills the space", () => {
  near(fitWidthScale(800, 400), 2, "800 over 400");
  near(fitWidthScale(10, 600), 0.25 * PX_PER_PT, "never below the smallest zoom");
});

test("zoom steps move up and down and stop at the ends", () => {
  near(stepZoom(1, 1), 1.25, "up from 1");
  near(stepZoom(1, -1), 0.9, "down from 1");
  near(stepZoom(4, 1), 4, "top");
  near(stepZoom(0.25, -1), 0.25, "bottom");
});

test("image width is bucketed and bounded", () => {
  near(imageWidthFor(595, 1.333, 1), 800, "A4 at 100%");
  near(imageWidthFor(595, 0.1, 1), 320, "floor");
  near(imageWidthFor(595, 10, 2), 3200, "ceiling");
});

test("boxes from corners are normalised", () => {
  const b = boxFromCorners({ x: 50, y: 40 }, { x: 10, y: 90 });
  near(b.x, 10, "x"); near(b.y, 40, "y"); near(b.w, 40, "w"); near(b.h, 50, "h");
});

test("moving keeps a box on the page", () => {
  const page = { w: 600, h: 800 };
  const moved = moveBox({ x: 500, y: 700, w: 80, h: 60 }, { x: 100, y: 100 }, page);
  near(moved.x, 520, "x"); near(moved.y, 740, "y");
  near(fitInside({ x: -5, y: -5, w: 10, h: 10 }, page).x, 0, "clamped left");
});

test("resizing from the south east corner grows the box", () => {
  const r = resizeBox({ x: 100, y: 100, w: 50, h: 40 }, "se", { x: 20, y: 10 }, { min: 6 });
  near(r.x, 100, "x"); near(r.w, 70, "w"); near(r.h, 50, "h");
});

test("resizing from the north west corner moves the origin", () => {
  const r = resizeBox({ x: 100, y: 100, w: 50, h: 40 }, "nw", { x: -10, y: -10 }, { min: 6 });
  near(r.x, 90, "x"); near(r.y, 90, "y"); near(r.w, 60, "w"); near(r.h, 50, "h");
});

test("resizing past the opposite edge stops at the minimum", () => {
  const r = resizeBox({ x: 100, y: 100, w: 50, h: 40 }, "e", { x: -200, y: 0 }, { min: 6 });
  near(r.x, 100, "x"); near(r.w, 6, "w");
  const l = resizeBox({ x: 100, y: 100, w: 50, h: 40 }, "w", { x: 200, y: 0 }, { min: 6 });
  near(l.x + l.w, 150, "right edge fixed"); near(l.w, 6, "w");
});

test("resizing stays inside the page", () => {
  const r = resizeBox({ x: 500, y: 700, w: 50, h: 40 }, "se", { x: 400, y: 400 }, { min: 6, page: { w: 600, h: 800 } });
  near(r.x + r.w, 600, "right"); near(r.y + r.h, 800, "bottom");
});

test("aspect ratio is kept from a corner", () => {
  const start = { x: 100, y: 100, w: 100, h: 50 };
  const r = resizeBox(start, "se", { x: 50, y: 0 }, { min: 6, keepAspect: true });
  near(r.w / r.h, 2, "ratio"); near(r.x, 100, "anchor x"); near(r.y, 100, "anchor y");
  const nw = resizeBox(start, "nw", { x: -50, y: 0 }, { min: 6, keepAspect: true });
  near(nw.w / nw.h, 2, "nw ratio"); near(nw.x + nw.w, 200, "anchor right");
});

test("aspect ratio resize never leaves the page", () => {
  const r = resizeBox({ x: 500, y: 700, w: 80, h: 40 }, "se", { x: 900, y: 900 }, { min: 6, keepAspect: true, page: { w: 600, h: 800 } });
  if (r.x + r.w > 600 + 1e-6 || r.y + r.h > 800 + 1e-6) throw new Error("outside page");
  near(r.w / r.h, 2, "ratio");
});

test("bounds and point remapping", () => {
  const b = boundsOf([{ x: 10, y: 20 }, { x: 30, y: 60 }]);
  near(b.x, 10, "x"); near(b.w, 20, "w"); near(b.h, 40, "h");
  const p = remapPoint({ x: 20, y: 40 }, b, { x: 100, y: 100, w: 200, h: 80 });
  samePt(p, { x: 200, y: 140 }, "centre");
  near(boundsOf([{ x: 5, y: 5 }]).w, 1, "single point gets size");
});

test("engine rectangles are rounded corner lists", () => {
  const r = toRect({ x: 10.126, y: 20, w: 30, h: 40.004 });
  near(r[0], 10.13, "x0"); near(r[2], 40.13, "x1"); near(r[3], 60, "y1");
});

export function runGeometryTests(): { passed: number; failures: string[] } {
  const failures: string[] = [];
  for (const [name, fn] of tests) {
    try {
      fn();
    } catch (error) {
      failures.push(`${name}: ${(error as Error).message}`);
    }
  }
  return { passed: tests.length - failures.length, failures };
}
