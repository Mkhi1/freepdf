"""Watermarks and page numbers: text or images placed at fixed positions on many pages."""
import io
import math

import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pymupdf

from ..core import ToolError, require, require_file
from . import _textfit as tf

POSITIONS = {
    "top-left": (0, 0), "top-center": (1, 0), "top-right": (2, 0),
    "middle-left": (0, 1), "center": (1, 1), "middle-right": (2, 1),
    "bottom-left": (0, 2), "bottom-center": (1, 2), "bottom-right": (2, 2),
}
ALIASES = {"middle-center": "center", "center-center": "center", "top": "top-center",
           "bottom": "bottom-center", "left": "middle-left", "right": "middle-right",
           "middle": "center", "centre": "center"}
NUMBER_MARGINS = {"small": 18.0, "recommended": 36.0, "big": 54.0}
ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
EDGE_MARGIN = 24.0


def grid_cell(position: str) -> tuple[int, int]:
    key = ALIASES.get(position, position)
    if key not in POSITIONS:
        raise ToolError("bad_args", f'"{position}" is not a position. Use one of: ' + ", ".join(POSITIONS))
    return POSITIONS[key]


def opacity_from(args: dict, default=0.5) -> float:
    value = float(args.get("opacity", default))
    value = value / 100 if value > 1 else value
    return min(max(value, 0.0), 1.0)


def turned_extent(width: float, height: float, angle: float) -> tuple[float, float]:
    rad = math.radians(angle)
    c, s = abs(math.cos(rad)), abs(math.sin(rad))
    return width * c + height * s, width * s + height * c


def anchor_centre(page_rect, cell, extent) -> pymupdf.Point:
    """Centre for an element of `extent` so that its turned outline stays inside the margins."""
    ew, eh = extent
    xs = (page_rect.x0 + EDGE_MARGIN + ew / 2, page_rect.x0 + page_rect.width / 2,
          page_rect.x1 - EDGE_MARGIN - ew / 2)
    ys = (page_rect.y0 + EDGE_MARGIN + eh / 2, page_rect.y0 + page_rect.height / 2,
          page_rect.y1 - EDGE_MARGIN - eh / 2)
    return pymupdf.Point(xs[cell[0]], ys[cell[1]])


def mosaic_centres(page_rect, extent) -> list[pymupdf.Point]:
    ew, eh = extent
    step_x, step_y = ew * 1.6 + 20, eh * 2.2 + 20
    cols = max(int(page_rect.width // step_x) + 2, 1)
    rows = max(int(page_rect.height // step_y) + 2, 1)
    centres = []
    for row in range(rows):
        offset = step_x / 2 if row % 2 else 0
        for col in range(cols):
            x = page_rect.x0 + col * step_x + offset - step_x / 4
            y = page_rect.y0 + row * step_y + step_y / 2 - step_y / 4
            if -ew <= x <= page_rect.x1 + ew and -eh <= y <= page_rect.y1 + eh:
                centres.append(pymupdf.Point(x, y))
    return centres


def load_watermark_image(args: dict) -> tuple[bytes, float]:
    """PNG bytes with opacity baked into the alpha channel, plus the aspect ratio."""
    from PIL import Image

    path = require_file(require(args, "image_path"))
    try:
        img = Image.open(path).convert("RGBA")
    except Exception as err:
        raise ToolError("bad_args", f"{path.name} could not be read as a picture.") from err
    opacity = opacity_from(args)
    alpha = img.getchannel("A").point(lambda a: int(a * opacity))
    img.putalpha(alpha)
    angle = float(args.get("rotation", 0))
    if angle % 360:
        img = img.rotate(angle, expand=True, resample=Image.BICUBIC)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue(), img.width / img.height


def watermark_page(page, args: dict, prepared: dict) -> None:
    rect = tf.visual_rect(page)
    angle = float(args.get("rotation", 0))
    overlay = args.get("layer", "over") != "under"
    if prepared["kind"] == "image":
        extent = _image_extent(rect, args, prepared["ratio"])
    else:
        extent = turned_extent(prepared["w"], prepared["h"], angle)
    if args.get("mosaic"):
        centres = mosaic_centres(rect, extent)
    else:
        centres = [anchor_centre(rect, grid_cell(args.get("position", "center")), extent)]
    for centre in centres:
        if prepared["kind"] == "image":
            _place_image(page, centre, extent, prepared["png"], overlay)
        else:
            _place_text(page, centre, prepared, args, angle, overlay)


def _image_extent(rect, args, ratio) -> tuple[float, float]:
    width = rect.width * float(args.get("scale", 0.4))
    height = width / ratio
    limit = rect.height * 0.9
    if height > limit:
        width, height = limit * ratio, limit
    return width, height


def _place_image(page, centre, extent, png, overlay) -> None:
    box = pymupdf.Rect(centre.x - extent[0] / 2, centre.y - extent[1] / 2,
                       centre.x + extent[0] / 2, centre.y + extent[1] / 2)
    page.insert_image(tf.native_rect(page, box), stream=png, overlay=overlay)


def _place_text(page, centre, prepared, args, angle, overlay) -> None:
    w, h = prepared["w"], prepared["h"]
    top_left = (centre.x - w / 2, centre.y - h / 2)
    tf.add_text(page, top_left, prepared["text"], size=prepared["size"], color=prepared["color"],
                font=args.get("font"), bold=bool(args.get("bold")), italic=bool(args.get("italic")),
                underline=bool(args.get("underline")), opacity=opacity_from(args), angle=angle,
                pivot=(centre.x, centre.y), overlay=overlay, width=w + prepared["size"] * 0.5)


def prepare_watermark(args: dict) -> dict:
    kind = args.get("kind", "text")
    if kind == "image":
        png, ratio = load_watermark_image(args)
        return {"kind": "image", "png": png, "ratio": ratio}
    text = str(require(args, "text"))
    size = float(args.get("size", 48))
    w, h, _ = tf.measure(text, size, args.get("font"), bool(args.get("bold")), bool(args.get("italic")))
    return {"kind": "text", "text": text, "size": size, "w": w + size * 0.2, "h": h,
            "color": tf.parse_color(args.get("color"), (0.5, 0.5, 0.5))}


def number_text(pattern: str, n: int, total: int, numerals: str) -> str:
    text = pattern.replace("{n}", str(n)).replace("{total}", str(total))
    return text.translate(ARABIC_DIGITS) if numerals == "arabic" else text


def number_cell(position: str, n: int, facing: bool) -> tuple[str, str]:
    vertical, _, horizontal = position.partition("-")
    if vertical not in ("top", "bottom") or horizontal not in ("left", "center", "right"):
        raise ToolError("bad_args", f'"{position}" is not a page number position. Use top-left, top-center, '
                                    "top-right, bottom-left, bottom-center or bottom-right.")
    if facing and n % 2 == 0 and horizontal != "center":
        horizontal = "left" if horizontal == "right" else "right"
    return vertical, horizontal


def place_number(page, text: str, args: dict, n: int) -> None:
    size = float(args.get("size", 12))
    bold, italic = bool(args.get("bold")), bool(args.get("italic"))
    margin = NUMBER_MARGINS.get(args.get("margin", "recommended"), NUMBER_MARGINS["recommended"])
    width, height, _ = tf.measure(text, size, args.get("font"), bold, italic)
    vertical, horizontal = number_cell(args.get("position", "bottom-center"), n, bool(args.get("facing")))
    rect = tf.visual_rect(page)
    x = {"left": rect.x0 + margin, "center": rect.x0 + (rect.width - width) / 2,
         "right": rect.x1 - margin - width}[horizontal]
    y = rect.y0 + margin if vertical == "top" else rect.y1 - margin - height
    tf.add_text(page, (x, y), text, size=size, color=tf.parse_color(args.get("color")), font=args.get("font"),
                bold=bold, italic=italic, width=width + size)
