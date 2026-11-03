"""Turns a hoopoe photo into an engraved icon: cut the bird out, then redraw its tones as ink lines."""
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

SIZE = 1024
SS = 2
WORK = SIZE * SS
INK = np.array((22, 19, 18), float)
IVORY = np.array((243, 236, 220), float)
TILE = (63, 184, 212)
CORNER = 232
LINE_PERIOD = 7.5
TONE_BEND = 22.0
TOP_MARGIN = 88
BIRD_WIDTH = 930
TRACE_SCALE = 0.45
HEAD_BOX = (436, 884, 132)
GROUND_TRACE = [
    (0, 740), (228, 746), (262, 708), (330, 704), (470, 690), (520, 650), (636, 612), (668, 604), (706, 640),
    (800, 700), (1238, 740), (1238, 828), (0, 828),
]

source, target = Path(sys.argv[1]), Path(sys.argv[2])
mask_preview = Path(sys.argv[3]) if len(sys.argv) > 3 else None


def background_distance(photo):
    lab = cv2.cvtColor(photo, cv2.COLOR_BGR2LAB).astype(np.float32)
    top = lab[: lab.shape[0] // 5]
    sky = np.median(top.reshape(-1, 3), axis=0)
    return np.linalg.norm(lab - sky, axis=2)


def largest_part(mask):
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count < 2:
        return mask
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.uint8(labels == best) * 255


def ground_mask(photo):
    """The mound in this photo, traced by hand. Colour alone confuses it with the black wing feathers."""
    points = np.array(GROUND_TRACE, float) / TRACE_SCALE
    width_scale = photo.shape[1] / 2750
    outline = np.int32(points * width_scale)
    mask = np.zeros(photo.shape[:2], np.uint8)
    cv2.fillPoly(mask, [outline], 255)
    return mask


def fill_holes(mask):
    contours_found, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(mask)
    cv2.drawContours(filled, contours_found, -1, 255, cv2.FILLED)
    return filled


def cut_out(photo):
    """GrabCut seeded from colour distance, with the ground marked as background."""
    distance = background_distance(photo)
    rough = np.uint8(distance > 14) * 255
    ground = ground_mask(photo)
    seed = np.full(photo.shape[:2], cv2.GC_PR_BGD, np.uint8)
    seed[distance < 6] = cv2.GC_BGD
    seed[rough > 0] = cv2.GC_PR_FGD
    seed[ground > 0] = cv2.GC_BGD
    core = cv2.erode(cv2.bitwise_and(rough, cv2.bitwise_not(ground)), np.ones((11, 11), np.uint8))
    seed[core > 0] = cv2.GC_FGD
    bgd, fgd = np.zeros((1, 65)), np.zeros((1, 65))
    cv2.grabCut(photo, seed, None, bgd, fgd, 4, cv2.GC_INIT_WITH_MASK)
    mask = np.uint8((seed == cv2.GC_FGD) | (seed == cv2.GC_PR_FGD)) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    return fill_holes(largest_part(mask))


def frame(photo, mask):
    """Scales the head onto the tile, top aligned, so the body runs off the bottom edge."""
    left, right, top = (value / TRACE_SCALE for value in HEAD_BOX)
    scale = (BIRD_WIDTH * SS) / (right - left + 1)
    matrix = np.float32([
        [scale, 0, (WORK - (right + left) * scale) / 2],
        [0, scale, TOP_MARGIN * SS - top * scale],
    ])
    size = (WORK, WORK)
    placed = cv2.warpAffine(photo, matrix, size, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    alpha = cv2.warpAffine(mask, matrix, size, flags=cv2.INTER_LINEAR)
    return placed, cv2.GaussianBlur(alpha, (0, 0), 1.6)


def tone_map(placed, alpha):
    gray = cv2.cvtColor(placed, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8)).apply(gray)
    inside = gray[alpha > 128]
    low, high = np.percentile(inside, (3, 97))
    return np.clip((gray.astype(np.float32) - low) / (high - low + 1e-6), 0, 1) ** 0.72


def engrave(tone):
    """Ink lines whose paths bend around the form and whose width follows the darkness."""
    height, width = tone.shape
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    smooth = cv2.GaussianBlur(tone, (0, 0), 14)
    direction = np.deg2rad(58)
    along = xs * np.cos(direction) + ys * np.sin(direction)
    phase = (along + TONE_BEND * SS * smooth) / (LINE_PERIOD * SS)
    wave = 0.5 + 0.5 * np.cos(2 * np.pi * phase)
    darkness = np.clip(1 - tone, 0, 1) ** 1.5
    return (wave < darkness * 1.1).astype(np.float32)


def contours(tone):
    """Fine detail lines from a difference of Gaussians, which keeps feather edges crisp."""
    fine = cv2.GaussianBlur(tone, (0, 0), 1.4)
    wide = cv2.GaussianBlur(tone, (0, 0), 3.4)
    return (fine - 0.985 * wide < -0.018).astype(np.float32)


def compose(placed, alpha):
    tone = tone_map(placed, alpha)
    ink = np.maximum(engrave(tone), contours(tone))
    ink = cv2.GaussianBlur(ink, (0, 0), 0.8)
    bird = IVORY[None, None, :] * (1 - ink[..., None]) + INK[None, None, :] * ink[..., None]
    edge = cv2.morphologyEx(np.uint8(alpha > 128) * 255, cv2.MORPH_GRADIENT, np.ones((7, 7), np.uint8))
    edge = cv2.GaussianBlur(edge.astype(np.float32) / 255, (0, 0), 1.0)[..., None]
    bird = bird * (1 - edge) + INK[None, None, :] * edge
    a = (alpha.astype(np.float32) / 255)[..., None]
    out = np.array(TILE, float)[None, None, :] * (1 - a) + bird * a
    return np.clip(out, 0, 255).astype(np.uint8)


def finish(pixels):
    tile = Image.new("L", (WORK, WORK), 0)
    ImageDraw.Draw(tile).rounded_rectangle([0, 0, WORK - 1, WORK - 1], CORNER * SS, fill=255)
    rgba = Image.fromarray(pixels, "RGB").convert("RGBA")
    rgba.putalpha(tile)
    return rgba.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    photo = cv2.imdecode(np.fromfile(source, np.uint8), cv2.IMREAD_COLOR)
    mask = cut_out(photo)
    if mask_preview:
        shown = photo.copy()
        shown[mask == 0] = (shown[mask == 0] * 0.25).astype(np.uint8)
        cv2.imencode(".jpg", cv2.resize(shown, None, fx=0.45, fy=0.45))[1].tofile(mask_preview)
    placed, alpha = frame(photo, mask)
    finish(compose(placed, alpha)).save(target)


if __name__ == "__main__":
    main()
