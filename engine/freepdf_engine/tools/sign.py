"""Sign: place signature images and text on a PDF, and draw a typed signature as a transparent PNG."""
import html
import io
import re
import warnings
from pathlib import Path

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pymupdf

from ..core import Job, ToolError, output_path, require, require_file, resource_dir, result
from ..registry import tool
from . import _textfit as tf
from ._mk_io import open_doc, save_doc, subset_fonts
from .markup import _edit_ink

SCALE = 4
HANDWRITING = {
    "script": "segoesc.ttf", "print": "segoepr.ttf", "ink": "Inkfree.ttf", "brush": "BRUSHSCI.TTF",
    "formal": "FRSCRIPT.TTF", "bold": "mvboli.ttf", "gabriola": "Gabriola.ttf",
}
ARABIC_HANDWRITING = ("aldhabi.ttf", "majalla.ttf", "arial.ttf")
DEFAULT_STYLE = "script"


def _signature_font(style: str | None, text: str) -> str:
    if tf.is_rtl(text):
        for name in ARABIC_HANDWRITING:
            if (tf.FONTS_DIR / name).is_file():
                return name
    name = HANDWRITING.get(str(style or DEFAULT_STYLE).lower(), HANDWRITING[DEFAULT_STYLE])
    if not (tf.FONTS_DIR / name).is_file():
        name = "arial.ttf"
    return name


def _alpha_png(path: str) -> bytes:
    from PIL import Image

    try:
        img = Image.open(path).convert("RGBA")
    except Exception as err:
        raise ToolError("bad_args", "The signature picture could not be read. Use a PNG or JPG file.") from err
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def _place_signature(page, item: dict) -> None:
    rect = tf.native_rect(page, pymupdf.Rect(item["rect"]))
    png = _alpha_png(str(require_file(item["image_path"])))
    page.insert_image(rect, stream=png, keep_proportion=True)


def _place_text_field(page, item: dict) -> None:
    tf.add_text(page, (float(item["x"]), float(item["y"])), str(item["text"]), size=float(item.get("size", 14)),
                font=item.get("font"), color=tf.parse_color(item.get("color")), bold=bool(item.get("bold")),
                italic=bool(item.get("italic")), width=item.get("width"))


@tool("sign")
def sign(job: Job, args: dict) -> dict:
    doc = open_doc(args)
    items = require(args, "items")
    placers = {"signature": _place_signature, "text_field": _place_text_field, "ink": _edit_ink}
    for index, item in enumerate(items):
        job.progress(index / len(items), f"Placing item {index + 1} of {len(items)}")
        place = placers.get(item.get("type"))
        page_no = item.get("page")
        if place is None:
            raise ToolError("bad_args", f'"{item.get("type")}" is not a signing item. Use signature, text_field or ink.')
        if not isinstance(page_no, int) or not 0 <= page_no < doc.page_count:
            raise ToolError("bad_args", f"An item points at page {page_no}, but this file has {doc.page_count} pages.")
        try:
            place(doc[page_no], item)
        except KeyError as err:
            raise ToolError("bad_args", f"A {item['type']} item is missing {err.args[0]}.") from err
    subset_fonts(doc)
    return result([save_doc(doc, args, "signed")], items=len(items))


def _render_signature(text: str, font_file: str, color, size: float) -> bytes:
    css = (f"@font-face{{font-family:sig;src:url({font_file});}}"
           f"body{{font-family:sig;font-size:{size}pt;color:{tf.css_color(color)};direction:"
           f"{'rtl' if tf.is_rtl(text) else 'ltr'};margin:0;white-space:nowrap;}}")
    scratch = pymupdf.open()
    sheet = scratch.new_page(width=size * (len(text) + 4) * 0.9 + 80, height=size * 2.6)
    sheet.insert_htmlbox(sheet.rect, html.escape(text), css=css, archive=pymupdf.Archive(str(tf.FONTS_DIR)),
                         scale_low=0)
    pix = sheet.get_pixmap(matrix=pymupdf.Matrix(SCALE, SCALE), alpha=True)
    scratch.close()
    return _crop_to_ink(pix.tobytes("png"))


def _crop_to_ink(png: bytes) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(png)).convert("RGBA")
    box = img.getchannel("A").getbbox()
    if box is None:
        raise ToolError("tool_failed", "The signature came out empty. Try different text or another style.")
    pad = 6 * SCALE
    left, top, right, bottom = box
    cropped = img.crop((max(left - pad, 0), max(top - pad, 0), min(right + pad, img.width),
                        min(bottom + pad, img.height)))
    out = io.BytesIO()
    cropped.save(out, "PNG")
    return out.getvalue()


def _signature_destination(args: dict, text: str) -> Path:
    folder = args.get("out_dir") or str(resource_dir("signatures"))
    slug = re.sub(r"\W+", "_", text, flags=re.UNICODE).strip("_")[:24] or "signature"
    return output_path(Path(folder) / f"signature_{slug}.png", "", ".png", folder)


@tool("make_signature")
def make_signature(job: Job, args: dict) -> dict:
    text = str(require(args, "text")).strip()
    if not text:
        raise ToolError("bad_args", "Type your name to make a signature.")
    font_file = _signature_font(args.get("font"), text)
    color = tf.parse_color(args.get("color"), (0.05, 0.1, 0.45))
    png = _render_signature(text, font_file, color, float(args.get("size", 44)))
    dest = _signature_destination(args, text)
    dest.write_bytes(png)
    return result([dest], font=font_file, path=str(dest))
