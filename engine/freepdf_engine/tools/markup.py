"""Edit, annotate, page numbers and watermark."""
import io

import pymupdf

from ..core import Job, ToolError, require, result
from ..registry import tool
from . import _stamp, _textfit as tf
from ._mk_io import open_doc, page_window, save_doc, subset_fonts


def _page_of(doc, item: dict):
    index = item.get("page")
    if not isinstance(index, int) or not 0 <= index < doc.page_count:
        raise ToolError("bad_args", f"An item points at page {index}, but this file has {doc.page_count} pages.")
    return doc[index]


def _native_points(page, points) -> list[pymupdf.Point]:
    return [tf.native_point(page, p) for p in points]


def _style(item: dict) -> dict:
    return {"color": tf.parse_color(item.get("color")), "size": float(item.get("size", 14)),
            "font": item.get("font"), "bold": bool(item.get("bold")), "italic": bool(item.get("italic")),
            "underline": bool(item.get("underline"))}


def _edit_text(page, item: dict) -> None:
    tf.add_text(page, (float(item["x"]), float(item["y"])), str(item["text"]),
                width=item.get("width"), opacity=float(item.get("opacity", 1)), **_style(item))


def _edit_image(page, item: dict) -> None:
    from PIL import Image

    rect = pymupdf.Rect(item["rect"])
    turn = float(item.get("rotate", 0)) % 360
    try:
        img = Image.open(item["path"]).convert("RGBA")
    except Exception as err:
        raise ToolError("bad_args", "One of the pictures could not be read. Pick a PNG or JPG file.") from err
    if turn:
        img = img.rotate(-turn, expand=True, resample=Image.BICUBIC)
        mid = (rect.tl + rect.br) / 2
        w, h = _stamp.turned_extent(rect.width, rect.height, turn)
        rect = pymupdf.Rect(mid.x - w / 2, mid.y - h / 2, mid.x + w / 2, mid.y + h / 2)
    buffer = io.BytesIO()
    img.save(buffer, "PNG")
    page.insert_image(tf.native_rect(page, rect), stream=buffer.getvalue(), keep_proportion=False)


def _edit_shape(page, item: dict) -> None:
    kind = item.get("kind", "rect")
    stroke = tf.parse_color(item.get("stroke"), (0, 0, 0)) if item.get("stroke", "#000000") else None
    fill = tf.parse_color(item["fill"]) if item.get("fill") else None
    width = float(item.get("width", 2))
    opacity = float(item.get("opacity", 1))
    shape = page.new_shape()
    r = pymupdf.Rect(item["rect"])
    if kind in ("line", "arrow"):
        start, end = _native_points(page, [item["rect"][:2], item["rect"][2:]])
        shape.draw_line(start, end)
        shape.finish(color=stroke, width=width, lineCap=1, stroke_opacity=opacity)
        if kind == "arrow":
            _arrow_head(page, shape, start, end, stroke, width, opacity)
    elif kind == "ellipse":
        shape.draw_oval(tf.native_rect(page, r))
        shape.finish(color=stroke, fill=fill, width=width, stroke_opacity=opacity, fill_opacity=opacity)
    elif kind == "rect":
        shape.draw_rect(tf.native_rect(page, r))
        shape.finish(color=stroke, fill=fill, width=width, stroke_opacity=opacity, fill_opacity=opacity)
    else:
        raise ToolError("bad_args", f'"{kind}" is not a shape. Use rect, ellipse, line or arrow.')
    shape.commit()


def _arrow_head(page, shape, start, end, stroke, width, opacity) -> None:
    direction = end - start
    if not direction.x and not direction.y:
        return
    unit = direction * (1 / max(abs(direction), 1e-6))
    size = max(width * 4, 10)
    back = end - unit * size
    normal = pymupdf.Point(-unit.y, unit.x) * (size * 0.45)
    shape.draw_polyline([back + normal, end, back - normal, back + normal])
    shape.finish(color=stroke, fill=stroke, width=1, closePath=True,
                 stroke_opacity=opacity, fill_opacity=opacity)


def _smooth(points: list[pymupdf.Point]) -> list[tuple]:
    """Catmull-Rom to Bezier segments through all points."""
    segments = []
    for i in range(len(points) - 1):
        p0 = points[max(i - 1, 0)]
        p1, p2 = points[i], points[i + 1]
        p3 = points[min(i + 2, len(points) - 1)]
        segments.append((p1, p1 + (p2 - p0) / 6, p2 - (p3 - p1) / 6, p2))
    return segments


def _edit_ink(page, item: dict) -> None:
    points = _native_points(page, item["points"])
    if len(points) < 2:
        return
    shape = page.new_shape()
    if len(points) == 2:
        shape.draw_line(*points)
    else:
        for seg in _smooth(points):
            shape.draw_bezier(*seg)
    shape.finish(color=tf.parse_color(item.get("color")), width=float(item.get("width", 2)),
                 lineCap=1, lineJoin=1, closePath=False, stroke_opacity=float(item.get("opacity", 1)))
    shape.commit()


def _edit_whiteout(page, item: dict) -> None:
    shape = page.new_shape()
    shape.draw_rect(tf.native_rect(page, item["rect"]))
    shape.finish(color=None, fill=tf.parse_color(item.get("color"), (1, 1, 1)), width=0)
    shape.commit()


EDIT_ITEMS = {"text": _edit_text, "image": _edit_image, "shape": _edit_shape,
              "ink": _edit_ink, "whiteout": _edit_whiteout}


@tool("edit")
def edit(job: Job, args: dict) -> dict:
    doc = open_doc(args)
    items = require(args, "items")
    for index, item in enumerate(items):
        job.progress(index / len(items), f"Adding item {index + 1} of {len(items)}")
        handler = EDIT_ITEMS.get(item.get("type"))
        if handler is None:
            raise ToolError("bad_args", f'"{item.get("type")}" is not something Edit can add.')
        try:
            handler(_page_of(doc, item), item)
        except KeyError as err:
            raise ToolError("bad_args", f"An {item['type']} item is missing {err.args[0]}.") from err
    subset_fonts(doc)
    out = save_doc(doc, args, "edited")
    return result([out], items=len(items))


def _quads_for(page, item: dict) -> list:
    if item.get("text"):
        found = page.search_for(str(item["text"]))
        return [q for q in found] if found else []
    rects = item.get("rects") or ([item["rect"]] if item.get("rect") else [])
    return [pymupdf.Rect(tf.native_rect(page, r)).quad for r in rects]


def _markup_annot(page, item: dict) -> None:
    adders = {"highlight": page.add_highlight_annot, "underline": page.add_underline_annot,
              "strikeout": page.add_strikeout_annot}
    default = {"highlight": (1, 0.92, 0.2), "underline": (0.1, 0.4, 0.9), "strikeout": (0.85, 0.1, 0.1)}
    kind = item["type"]
    quads = _quads_for(page, item)
    if not quads:
        return
    annot = adders[kind](quads=quads)
    annot.set_colors(stroke=tf.parse_color(item.get("color"), default[kind]))
    if kind == "highlight":
        annot.set_opacity(float(item.get("opacity", 0.5)))
    annot.set_info(title="Free PDF", content=str(item.get("content", "")))
    annot.update()


def _note_annot(page, item: dict) -> None:
    annot = page.add_text_annot(tf.native_point(page, (item["x"], item["y"])), str(item.get("text", "")))
    annot.set_colors(stroke=tf.parse_color(item.get("color"), (1, 0.85, 0.1)))
    annot.set_info(title="Free PDF")
    annot.update()


def _ink_annot(page, item: dict) -> None:
    strokes = item.get("strokes") or [item["points"]]
    native = [[tuple(tf.native_point(page, p)) for p in stroke] for stroke in strokes]
    annot = page.add_ink_annot(native)
    annot.set_colors(stroke=tf.parse_color(item.get("color"), (0.9, 0.1, 0.1)))
    annot.set_border(width=float(item.get("width", 2)))
    annot.set_info(title="Free PDF")
    annot.update()


def _freetext_annot(page, item: dict) -> None:
    rect = pymupdf.Rect(item["rect"])
    text = str(item["text"])
    style = _style(item)
    if tf.is_rtl(text):
        tf.fit_text_in_rect(page, rect, text, size=style["size"], color=style["color"],
                            font=style["font"], bold=style["bold"], italic=style["italic"],
                            align="right")
        return
    base = {"arial": "helv", "helvetica": "helv", "times": "tiro", "courier": "cour"}
    annot = page.add_freetext_annot(tf.native_rect(page, rect), text, fontsize=style["size"],
                                    fontname=base.get(str(style["font"] or "arial").lower(), "helv"),
                                    text_color=style["color"],
                                    fill_color=tf.parse_color(item["fill"]) if item.get("fill") else None,
                                    align=0)
    annot.set_info(title="Free PDF")
    annot.update()


ANNOT_ITEMS = {"highlight": _markup_annot, "underline": _markup_annot, "strikeout": _markup_annot,
               "note": _note_annot, "ink": _ink_annot, "freetext": _freetext_annot}


@tool("annotate")
def annotate(job: Job, args: dict) -> dict:
    doc = open_doc(args)
    items = require(args, "items")
    for index, item in enumerate(items):
        job.progress(index / len(items), f"Adding annotation {index + 1} of {len(items)}")
        handler = ANNOT_ITEMS.get(item.get("type"))
        if handler is None:
            raise ToolError("bad_args", f'"{item.get("type")}" is not an annotation type.')
        try:
            handler(_page_of(doc, item), item)
        except KeyError as err:
            raise ToolError("bad_args", f"A {item['type']} annotation is missing {err.args[0]}.") from err
    out = save_doc(doc, args, "annotated")
    return result([out], annotations=len(items))


@tool("page_numbers")
def page_numbers(job: Job, args: dict) -> dict:
    doc = open_doc(args)
    pages = page_window(args, doc.page_count)
    first = int(args.get("first_number", 1))
    total = first + len(pages) - 1
    pattern = str(args.get("format") or "{n}")
    numerals = args.get("numerals", "latin")
    for step, index in enumerate(pages):
        job.progress(step / len(pages), f"Numbering page {index + 1}")
        number = first + step
        _stamp.place_number(doc[index], _stamp.number_text(pattern, number, total, numerals), args, number)
    subset_fonts(doc)
    out = save_doc(doc, args, "numbered")
    return result([out], numbered=len(pages), first=first, last=total)


@tool("watermark")
def watermark(job: Job, args: dict) -> dict:
    doc = open_doc(args)
    pages = page_window(args, doc.page_count)
    prepared = _stamp.prepare_watermark(args)
    for step, index in enumerate(pages):
        job.progress(step / len(pages), f"Watermarking page {index + 1}")
        _stamp.watermark_page(doc[index], args, prepared)
    subset_fonts(doc)
    out = save_doc(doc, args, "watermarked")
    return result([out], pages=len(pages))
