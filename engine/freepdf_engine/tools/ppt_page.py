"""Page analysis for PDF to PowerPoint: a text-free background picture plus editable text blocks."""
import io
import re
from dataclasses import dataclass

import numpy as np
import pymupdf
from PIL import Image

ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")
STYLE_TAIL = re.compile(r"(MT|PS|PSMT)?([-,](Bold|Italic|Regular|BoldItalic|Oblique|BoldOblique|Roman|Medium|Semibold|Light))*$", re.I)
CONTROL = re.compile("[" + "".join(chr(c) for c in [*range(0, 9), *range(11, 32)]) + "￾￿]")
BOLD, ITALIC = 16, 2
MAX_PICTURE_DPI = 300
MAX_PICTURE_PIXELS = 40_000_000
MAX_OTHER_INK = 0.03  # on real pages plain text left under 2% outside its lines, designed pages 4% or more
PAPER_TOLERANCE = 40  # colour distance from the page background that still counts as paper
INK_CHECK_PX = 800


@dataclass(frozen=True)
class Run:
    text: str
    font: str
    size: float
    color: int
    bold: bool
    italic: bool


@dataclass(frozen=True)
class Block:
    lines: tuple[tuple[Run, ...], ...]
    bbox: tuple[float, float, float, float]
    line_boxes: tuple[tuple[float, float, float, float], ...]
    rtl: bool
    align: str  # left, center or right
    pitch: float  # baseline to baseline distance in points
    angle: float  # text rotation in degrees, 0 for horizontal


def family(name: str) -> str:
    base = SUBSET_PREFIX.sub("", name)
    base = STYLE_TAIL.sub("", base).replace("-", " ").strip()
    base = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base) if " " not in base else base
    return base or "Arial"


def _run(span: dict) -> Run:
    name = span["font"]
    bold = bool(span["flags"] & BOLD) or bool(re.search(r"bold|black|heavy", name, re.I))
    italic = bool(span["flags"] & ITALIC) or bool(re.search(r"italic|oblique", name, re.I))
    return Run(CONTROL.sub("", span["text"]), family(name), float(span["size"]), int(span["color"]), bold, italic)


def _alignment(boxes: list[tuple], rtl: bool) -> str:
    if len(boxes) < 2:
        return "right" if rtl else "left"
    lefts, rights = [b[0] for b in boxes], [b[2] for b in boxes]
    centers = [(b[0] + b[2]) / 2 for b in boxes]
    spread = lambda values: max(values) - min(values)
    if spread(lefts) <= 2.5 and not (rtl and spread(rights) <= 2.5):
        return "left"
    if spread(rights) <= 2.5:
        return "right"
    return "center" if spread(centers) <= 2.5 else ("right" if rtl else "left")


def _pitch(lines: list[dict], size: float) -> float:
    origins = [line["spans"][0]["origin"][1] for line in lines if line["spans"]]
    steps = [b - a for a, b in zip(origins, origins[1:]) if b - a > 0.5]
    return float(np.median(steps)) if steps else size * 1.2


def _angle(line: dict) -> float:
    dx, dy = line["dir"]
    return float(np.degrees(np.arctan2(-dy, dx))) if abs(dy) > 0.02 else 0.0


def text_blocks(page: pymupdf.Page) -> list[Block]:
    blocks = []
    for raw in page.get_text("dict")["blocks"]:
        if raw["type"] != 0:
            continue
        lines = [ln for ln in raw["lines"] if any(s["text"].strip() for s in ln["spans"])]
        if not lines:
            continue
        runs = tuple(tuple(_run(s) for s in ln["spans"] if s["text"]) for ln in lines)
        sample = "".join(r.text for line in runs for r in line)
        letters = [c for c in sample if c.isalpha()]
        rtl = bool(letters) and sum(1 for c in letters if ARABIC.match(c)) / len(letters) > 0.5
        boxes = [tuple(ln["bbox"]) for ln in lines]
        size = max(r.size for line in runs for r in line)
        blocks.append(Block(runs, tuple(raw["bbox"]), tuple(boxes), rtl, _alignment(boxes, rtl), _pitch(lines, size), _angle(lines[0])))
    return blocks


def has_only_invisible_text(page: pymupdf.Page) -> bool:
    trace = page.get_texttrace()
    return bool(trace) and all(t.get("type") == 3 or t.get("opacity", 1) == 0 for t in trace)


def strip_text(doc: pymupdf.Document, index: int) -> pymupdf.Document:
    """A one-page copy of the page with its text removed; images and vector graphics stay."""
    single = pymupdf.open()
    single.insert_pdf(doc, from_page=index, to_page=index)
    page = single[0]
    for raw in page.get_text("dict")["blocks"]:
        for line in raw.get("lines", []) if raw["type"] == 0 else []:
            for span in line["spans"]:
                rect = pymupdf.Rect(span["bbox"])
                shrink = rect.height * 0.12
                page.add_redact_annot(pymupdf.Rect(rect.x0, rect.y0 + shrink, rect.x1, rect.y1 - shrink), fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    return single


def _render(page: pymupdf.Page, dpi: float) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def inpaint(img: Image.Image, rects: list[pymupdf.Rect], scale: float) -> Image.Image:
    """Paint over text lines baked into a scan using the median colour just outside each line."""
    pixels = np.asarray(img).copy()
    height, width = pixels.shape[:2]
    for rect in rects:
        x0, y0 = max(int(rect.x0 * scale) - 1, 0), max(int(rect.y0 * scale) - 1, 0)
        x1, y1 = min(int(rect.x1 * scale) + 1, width), min(int(rect.y1 * scale) + 1, height)
        pad = 4
        ring = pixels[max(y0 - pad, 0):min(y1 + pad, height), max(x0 - pad, 0):min(x1 + pad, width)].reshape(-1, 3)
        inner = pixels[y0:y1, x0:x1].reshape(-1, 3)
        background = np.median(np.concatenate([ring, inner[inner.sum(axis=1) > np.median(inner.sum(axis=1))]]), axis=0)
        pixels[y0:y1, x0:x1] = background
    return Image.fromarray(pixels)


def _page_dpi(page: pymupdf.Page, long_side_px: int) -> int:
    return int(min(long_side_px / (max(page.rect.width, page.rect.height) / 72), 200))


def _encode(image: Image.Image, jpeg_quality: int) -> tuple[bytes, str]:
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=False)
    if buffer.tell() > 1_500_000:
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=jpeg_quality)
        return buffer.getvalue(), "jpg"
    return buffer.getvalue(), "png"


def _line_rects(page: pymupdf.Page) -> list[pymupdf.Rect]:
    return [pymupdf.Rect(ln["bbox"]) for b in page.get_text("dict")["blocks"] if b["type"] == 0 for ln in b["lines"]]


def other_ink_share(page: pymupdf.Page) -> float:
    """Share of the page that is neither plain background nor inside a recognised line of text."""
    image = _render(page, max(int(min(72, INK_CHECK_PX * 72 / max(page.rect.width, page.rect.height))), 1))
    scale = image.width / page.rect.width
    pixels = np.asarray(image, dtype=np.int16)
    background = np.median(pixels.reshape(-1, 3), axis=0)
    ink = np.abs(pixels - background).max(axis=2) > PAPER_TOLERANCE
    for rect in _line_rects(page):
        x0, y0, x1, y1 = (max(int(v * scale), 0) for v in (rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2))
        ink[y0:y1, x0:x1] = False
    return float(ink.mean())


def background_bytes(doc: pymupdf.Document, index: int, long_side_px: int = 2400) -> tuple[bytes, str]:
    """Picture of the page without its text, as (bytes, extension)."""
    original = doc[index]
    invisible = has_only_invisible_text(original)
    dpi = _page_dpi(original, long_side_px)
    if invisible:
        image = inpaint(_render(original, dpi), _line_rects(original), dpi / 72)
    else:
        stripped = strip_text(doc, index)
        image = _render(stripped[0], dpi)
        stripped.close()
    return _encode(image, jpeg_quality=88)


def _image_dpi(page: pymupdf.Page) -> float:
    """Resolution of the sharpest picture on the page. Long side against long side, so rotation does not matter."""
    placed = [(max(i["width"], i["height"]), pymupdf.Rect(i["bbox"])) for i in page.get_image_info()]
    return max((pixels / max(box.width, box.height) * 72 for pixels, box in placed if not box.is_empty), default=0.0)


def _picture_dpi(page: pymupdf.Page, long_side_px: int) -> int:
    """As sharp as the pictures inside the page, without letting a poster sized page exhaust memory."""
    wanted = min(max(_page_dpi(page, long_side_px), _image_dpi(page)), MAX_PICTURE_DPI)
    square_inches = page.rect.width * page.rect.height / (72 * 72)
    return int(min(wanted, (MAX_PICTURE_PIXELS / square_inches) ** 0.5))


def page_picture(page: pymupdf.Page, long_side_px: int = 2400) -> tuple[bytes, str]:
    """The page exactly as the PDF shows it, as sharp as the pictures inside it, as (bytes, extension)."""
    return _encode(_render(page, _picture_dpi(page, long_side_px)), jpeg_quality=92)
