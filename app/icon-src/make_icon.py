"""Draws the Free PDF app icon: an original engraved hoopoe carrying a PDF page."""
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SIZE = 1024
SS = 2
W = SIZE * SS
INK = (18, 18, 20)
IVORY = (241, 236, 222)
TILE = (63, 184, 212)
CORNER = 232
OUT = Path(sys.argv[1])
FONT = r"C:\Windows\Fonts\georgiab.ttf"

BODY = [
    (352, 418), (392, 370), (456, 344), (530, 350), (588, 396), (624, 470), (668, 560), (744, 650),
    (824, 760), (890, 880), (940, 1060), (292, 1060), (280, 900), (302, 780), (346, 672), (386, 592),
    (374, 520), (346, 462),
]
WING = [
    (548, 640), (632, 600), (736, 672), (826, 790), (884, 910), (910, 1060), (510, 1060), (486, 880), (506, 730),
]
BEAK_TOP = [(356, 416), (276, 432), (196, 476), (112, 548)]
BEAK_BOTTOM = [(112, 548), (204, 508), (280, 480), (352, 464)]


def sc(p):
    return (float(p[0]) * SS, float(p[1]) * SS)


def catmull(points, closed=True, steps=14):
    pts = [np.array(p, float) for p in points]
    count = len(pts)
    out = []
    for i in range(count if closed else count - 1):
        p0 = pts[(i - 1) % count] if closed or i > 0 else pts[i]
        p1, p2 = pts[i], pts[(i + 1) % count]
        p3 = pts[(i + 2) % count] if closed or i + 2 < count else p2
        for k in range(steps):
            t = k / steps
            out.append(0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (3 * p1 - p0 - 3 * p2 + p3) * t ** 3))
    if not closed:
        out.append(pts[-1])
    return out


def mask_of(poly):
    im = Image.new("L", (W, W), 0)
    ImageDraw.Draw(im).polygon([sc(p) for p in poly], fill=255)
    return im


def stroke(draw, pts, width, taper=True, fill=255):
    """A hand-cut line: thick in the middle, tapering to points at both ends."""
    pts = np.array(pts, float)
    if len(pts) < 2:
        return
    tangents = np.gradient(pts, axis=0)
    lengths = np.linalg.norm(tangents, axis=1, keepdims=True)
    normals = np.stack([-tangents[:, 1], tangents[:, 0]], axis=1) / np.maximum(lengths, 1e-6)
    t = np.linspace(0, 1, len(pts))
    profile = np.sin(np.pi * t) ** 0.55 if taper else np.ones_like(t)
    half = (width / 2 * profile)[:, None]
    outline = np.concatenate([pts + normals * half, (pts - normals * half)[::-1]])
    draw.polygon([sc(p) for p in outline], fill=fill)


def line_through(a, b, bend=0.0, steps=8):
    a, b = np.array(a, float), np.array(b, float)
    mid = (a + b) / 2 + np.array([-(b - a)[1], (b - a)[0]]) * bend
    return [(1 - t) ** 2 * a + 2 * t * (1 - t) * mid + t ** 2 * b for t in np.linspace(0, 1, steps)]


class Canvas:
    def __init__(self):
        self.img = Image.new("RGB", (W, W), TILE)

    def fill(self, mask, color):
        self.img.paste(color, (0, 0), mask)

    def ink(self, painter, clip=None, color=INK):
        layer = Image.new("L", (W, W), 0)
        painter(ImageDraw.Draw(layer))
        self.img.paste(color, (0, 0), ImageChops.multiply(layer, clip) if clip else layer)


def outline(draw, poly, width):
    points = [sc(p) for p in poly]
    draw.line(points + points[:2], fill=255, width=int(width * SS), joint="curve")


def feather_poly(base, angle, length, width, bend):
    t = np.linspace(0, 1, 120)
    direction = np.array([math.cos(angle), math.sin(angle)])
    normal = np.array([-direction[1], direction[0]])
    spine = [np.array(base) + direction * length * s + normal * bend * length * s * s for s in t]
    shape = width / 2 * (0.34 + 0.66 * np.sin(np.pi * np.minimum(t * 0.62 + 0.12, 1)) ** 0.8)
    rounding = np.clip((t - 0.9) / 0.1, 0, 1)
    shape = shape * np.sqrt(1 - rounding ** 2)
    left = [p + normal * w for p, w in zip(spine, shape)]
    right = [p - normal * w for p, w in zip(spine, shape)]
    return spine, left, right, normal


def draw_feather(canvas, base, angle, length, width, bend):
    spine, left, right, normal = feather_poly(base, angle, length, width, bend)
    poly = left + right[::-1]
    mask = mask_of(poly)
    canvas.fill(mask, IVORY)
    tip_from = int(len(spine) * 0.74)

    def barbs(d):
        for i in range(6, tip_from - 21, 3):
            for side, edge in ((1, left), (-1, right)):
                a = spine[i]
                b = edge[min(i + 15, len(edge) - 1)]
                stroke(d, line_through(a, b, 0.05 * side), 3.2 + 2.6 * (1 - i / tip_from))

    def tip(d):
        d.polygon([sc(p) for p in left[tip_from:] + right[tip_from:][::-1]], fill=255)

    canvas.ink(barbs, mask)
    canvas.ink(tip, mask)
    canvas.ink(lambda d: outline(d, poly, 4.5))
    canvas.ink(lambda d: stroke(d, spine[:tip_from], 4.5, taper=False))


def draw_crest(canvas):
    count = 11
    order = sorted(range(count), key=lambda i: -abs(i - count / 2))
    for i in order:
        t = i / (count - 1)
        base = (402 + 188 * t, 372 + 26 * t ** 2 - 40 * math.sin(math.pi * t) * 0.5)
        angle = math.radians(-150 + 128 * t)
        length = 182 + 118 * math.sin(math.pi * t) ** 0.8
        draw_feather(canvas, base, angle, length, 74, 0.10 * (t - 0.5))


def ticks(canvas, clip, flow, shade, spacing, seed, lengths=(10, 34), widths=(1.6, 6.0)):
    rng = random.Random(seed)
    inside = np.array(clip.resize((SIZE, SIZE)))

    def paint(d):
        for y in range(0, SIZE, spacing):
            offset = spacing // 2 if (y // spacing) % 2 else 0
            for x in range(offset, SIZE, spacing):
                px = x + rng.uniform(-3, 3)
                py = y + rng.uniform(-3, 3)
                if not (0 <= px < SIZE and 0 <= py < SIZE) or inside[int(py), int(px)] < 128:
                    continue
                dark = shade(px, py)
                if dark < 0.14 or rng.random() > dark + 0.35:
                    continue
                angle = flow(px, py) + rng.uniform(-0.12, 0.12)
                size = lengths[0] + (lengths[1] - lengths[0]) * dark
                end = (px + math.cos(angle) * size, py + math.sin(angle) * size)
                stroke(d, line_through((px, py), end, 0.14), widths[0] + (widths[1] - widths[0]) * dark)

    canvas.ink(paint, clip)


def edge_shade(mask, radius):
    blurred = mask.filter(ImageFilter.GaussianBlur(radius * SS)).resize((SIZE, SIZE))
    return np.array(blurred, float) / 255


def draw_body(canvas):
    body = catmull(BODY)
    mask = mask_of(body)
    canvas.fill(mask, IVORY)
    wing = catmull(WING)
    wing_mask = mask_of(wing)
    plumage = ImageChops.subtract(mask, wing_mask)
    depth = edge_shade(mask, 46)

    def shade(x, y):
        light = math.hypot(x - 430, y - 520) / 560
        rim = 1 - min((depth[int(y), int(x)] - 0.5) * 2, 1)
        return float(np.clip(light * 0.72 + rim * 0.62, 0, 1))

    def flow(x, y):
        return math.radians(100 - (x - 520) * 0.11 + (y - 700) * 0.02)

    ticks(canvas, plumage, flow, shade, 15, 7)
    draw_wing(canvas, wing, wing_mask)
    canvas.ink(lambda d: outline(d, body, 7))


def draw_wing(canvas, wing, mask):
    canvas.fill(mask, IVORY)
    center = (1120, 470)

    def bars(d):
        for i, radius in enumerate(range(300, 980, 86)):
            for r in (radius,):
                arc = [(center[0] + r * math.cos(a), center[1] + r * math.sin(a))
                       for a in np.linspace(math.radians(60), math.radians(200), 90)]
                stroke(d, arc, 46, taper=False)

    canvas.ink(bars, mask)

    def scratches(d):
        for radius in range(300, 980, 86):
            for a in np.arange(math.radians(70), math.radians(195), 0.024):
                r0, r1 = radius - 19, radius + 19
                drift = 0.012
                start = (center[0] + r0 * math.cos(a), center[1] + r0 * math.sin(a))
                end = (center[0] + r1 * math.cos(a + drift), center[1] + r1 * math.sin(a + drift))
                stroke(d, line_through(start, end, 0.04), 2.6)

    canvas.ink(scratches, mask, IVORY)

    def scales(d):
        for row, y in enumerate(range(612, 730, 30)):
            for x in range(520, 780, 46):
                cx = x + (row % 2) * 23
                arc = [(cx + 24 * math.cos(a), y + 24 * math.sin(a)) for a in np.linspace(0.2, 2.9, 14)]
                d.polygon([sc(p) for p in arc], fill=255)

    def scale_lines(d):
        for row, y in enumerate(range(612, 730, 30)):
            for x in range(520, 780, 46):
                cx = x + (row % 2) * 23
                stroke(d, [(cx + 24 * math.cos(a), y + 24 * math.sin(a)) for a in np.linspace(0.1, 3.0, 16)], 6)

    top = mask_of([(480, 560), (800, 560), (800, 722), (480, 700)])
    shoulder = ImageChops.multiply(mask, top)
    canvas.ink(scales, shoulder, IVORY)
    canvas.ink(scale_lines, shoulder)
    canvas.ink(lambda d: outline(d, wing, 7))


def draw_head(canvas):
    head = mask_of(catmull([(350, 420), (392, 372), (456, 346), (540, 350), (604, 420), (600, 520), (500, 590), (390, 590), (370, 510)]))
    body = mask_of(catmull(BODY))
    clip = ImageChops.multiply(head, body)

    def shade(x, y):
        return float(np.clip(math.hypot(x - 430, y - 400) / 210, 0, 1)) ** 1.4

    ticks(canvas, clip, lambda x, y: math.radians(14 + (y - 430) * 0.25), shade, 12, 3, (8, 22), (1.6, 4.4))
    eye = (432, 412)

    def ring(d):
        d.ellipse([sc((eye[0] - 34, eye[1] - 34)), sc((eye[0] + 34, eye[1] + 34))], fill=255)

    canvas.ink(ring)

    def socket(d):
        d.ellipse([sc((eye[0] - 28, eye[1] - 28)), sc((eye[0] + 28, eye[1] + 28))], fill=255)

    canvas.ink(socket, None, IVORY)
    canvas.ink(lambda d: d.ellipse([sc((eye[0] - 21, eye[1] - 21)), sc((eye[0] + 21, eye[1] + 21))], fill=255))
    canvas.ink(lambda d: d.ellipse([sc((eye[0] - 13, eye[1] - 14)), sc((eye[0] - 2, eye[1] - 3))], fill=255), None, IVORY)


def draw_page(canvas):
    angle = math.radians(-6)
    origin = np.array([132.0, 536.0])
    rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    place = lambda x, y: tuple(origin + rotation @ np.array([x, y], float))
    w, h, fold = 92, 236, 46
    sheet = [place(-w, 0), place(w, 0), place(w, h - fold), place(w - fold, h), place(-w, h)]
    canvas.fill(mask_of(sheet), IVORY)
    canvas.ink(lambda d: d.polygon([sc(p) for p in [place(w - fold, h), place(w - fold, h - fold), place(w, h - fold)]], fill=255))

    def lines(d):
        for row, width in enumerate((1.0, 0.86, 0.94)):
            y = 138 + row * 26
            stroke(d, line_through(place(-w + 24, y), place(-w + 24 + (2 * w - 48) * width - 14 * (row == 2), y), 0.004), 8)

    def hatch(d):
        for x in range(-w + 6, w - 44, 11):
            stroke(d, line_through(place(x, h - 42 + (x % 3) * 4), place(x + 6, h - 6), 0.02), 4)

    canvas.ink(lines)
    canvas.ink(hatch, mask_of(sheet))
    canvas.ink(lambda d: outline(d, sheet, 7))
    text = Image.new("L", (W, W), 0)
    label = Image.new("L", (360 * SS, 120 * SS), 0)
    font = ImageFont.truetype(FONT, 62 * SS)
    ImageDraw.Draw(label).text((180 * SS, 60 * SS), "PDF", font=font, fill=255, anchor="mm")
    turned = label.rotate(6, resample=Image.BICUBIC)
    spot = place(0, 84)
    text.paste(turned, (int(spot[0] * SS - 180 * SS), int(spot[1] * SS - 60 * SS)))
    canvas.ink(lambda d: None)
    canvas.img.paste(INK, (0, 0), text)


def draw_beak(canvas):
    top = catmull(BEAK_TOP, closed=False)
    bottom = catmull(BEAK_BOTTOM, closed=False)
    poly = top + bottom[1:]
    canvas.fill(mask_of(poly), INK)
    midline = [(a + b) / 2 for a, b in zip(top, bottom[::-1])]
    canvas.ink(lambda d: stroke(d, midline[2:-8], 4.5), None, IVORY)
    upper = [p + np.array([0, 9]) for p in top[6:-14]]
    canvas.ink(lambda d: stroke(d, upper, 5), None, IVORY)


def finish(canvas):
    tile = Image.new("L", (W, W), 0)
    ImageDraw.Draw(tile).rounded_rectangle([0, 0, W - 1, W - 1], CORNER * SS, fill=255)
    rgba = canvas.img.convert("RGBA")
    rgba.putalpha(tile)
    return rgba.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    canvas = Canvas()
    draw_crest(canvas)
    draw_body(canvas)
    draw_head(canvas)
    draw_page(canvas)
    draw_beak(canvas)
    finish(canvas).save(OUT)


if __name__ == "__main__":
    main()
