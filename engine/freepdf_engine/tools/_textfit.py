"""Shared text drawing for the mark-up tools: Latin text through insert_text,
Arabic and other right-to-left text through insert_htmlbox so letters shape and join."""
import html
import io
import re
from pathlib import Path

import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pymupdf

from ..core import ToolError

RTL_RE = re.compile("[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufefc]")
FONTS_DIR = Path(r"C:\Windows\Fonts")
FAMILIES = {
    "arial": ("arial", "arialbd", "ariali", "arialbi"),
    "helvetica": ("arial", "arialbd", "ariali", "arialbi"),
    "times": ("times", "timesbd", "timesi", "timesbi"),
    "courier": ("cour", "courbd", "couri", "courbi"),
    "segoe ui": ("segoeui", "segoeuib", "segoeuii", "segoeuiz"),
    "tahoma": ("tahoma", "tahomabd", "tahoma", "tahomabd"),
    "verdana": ("verdana", "verdanab", "verdanai", "verdanaz"),
    "calibri": ("calibri", "calibrib", "calibrii", "calibriz"),
}
RTL_SAFE = ("arial", "times", "segoe ui", "tahoma")
BASE14 = {
    "arial": "helv", "helvetica": "helv", "times": "tiro", "courier": "cour",
}
BASE14_STYLES = {
    "helv": ("helv", "hebo", "heit", "hebi"),
    "tiro": ("tiro", "tibo", "tiit", "tibi"),
    "cour": ("cour", "cobo", "coit", "cobi"),
}
ASCENT_FALLBACK = 0.9


def is_rtl(text: str) -> bool:
    return bool(RTL_RE.search(text or ""))


def base_is_rtl(text: str) -> bool:
    """Paragraph direction follows the first letter, so "Page ٥" stays left to right."""
    for char in text or "":
        if char.isalpha():
            return bool(RTL_RE.match(char))
    return is_rtl(text)


def parse_color(value, default=(0, 0, 0)) -> tuple[float, float, float]:
    if value is None:
        return default
    if isinstance(value, str):
        match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
        if not match:
            raise ToolError("bad_args", f'"{value}" is not a colour. Use a form like #ff0000.')
        raw = match.group(1)
        return tuple(int(raw[i:i + 2], 16) / 255 for i in (0, 2, 4))
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(v / 255 if max(value) > 1 else float(v) for v in value)
    raise ToolError("bad_args", "Colour must be a hex string like #ff0000.")


def css_color(rgb) -> str:
    return "#%02x%02x%02x" % tuple(round(c * 255) for c in rgb)


def family_key(font: str | None, rtl: bool) -> str:
    key = (font or "arial").strip().lower()
    key = "arial" if key in ("", "default") else key
    if key not in FAMILIES:
        key = "arial"
    if rtl and key not in RTL_SAFE:
        key = "arial"
    return key


def font_file(font: str | None, bold: bool, italic: bool, rtl: bool = False) -> Path:
    key = family_key(font, rtl)
    names = FAMILIES[key]
    path = FONTS_DIR / f"{names[(1 if bold else 0) + (2 if italic else 0)]}.ttf"
    if not path.is_file():
        path = FONTS_DIR / "arial.ttf"
    if not path.is_file():
        raise ToolError("missing_resource", "The Windows font Arial was not found, so text cannot be added.")
    return path


def needs_unicode(text: str) -> bool:
    try:
        text.encode("latin-1")
        return False
    except UnicodeEncodeError:
        return True


def native_point(page, point) -> pymupdf.Point:
    return pymupdf.Point(point) * page.derotation_matrix


def native_rect(page, rect) -> pymupdf.Rect:
    return (pymupdf.Rect(rect) * page.derotation_matrix).normalize()


def visual_rect(page) -> pymupdf.Rect:
    return page.rect  # PyMuPDF already reports the rotated (viewer) size


def measure(text: str, size: float, font: str | None, bold: bool, italic: bool) -> tuple[float, float, str]:
    """Width and height of the widest line block, and the font file used."""
    rtl = is_rtl(text)
    path = font_file(font, bold, italic, rtl)
    lines = text.split("\n")
    if rtl:
        return _measure_rtl(text, size, font, bold, italic), size * 1.25 * len(lines), str(path)
    face = pymupdf.Font(fontfile=str(path))
    width = max(face.text_length(line, size) for line in lines)
    return width, size * 1.25 * len(lines), str(path)


def _measure_rtl(text, size, font, bold, italic) -> float:
    """Ink width of shaped text, found by laying it out on a scratch page."""
    scratch = pymupdf.open()
    sheet = scratch.new_page(width=4000, height=size * 3 * (text.count("\n") + 1))
    _html(sheet, sheet.rect, text, size, (0, 0, 0), font, bold, italic, False, 1.0, 0, True, "left", 1.0)
    spans = [s for b in sheet.get_text("dict")["blocks"] for ln in b.get("lines", []) for s in ln["spans"]]
    scratch.close()
    if not spans:
        return size * len(text) * 0.6
    return max(s["bbox"][2] for s in spans) - min(s["bbox"][0] for s in spans)


def _spec(font, bold, italic, text):
    key = family_key(font, is_rtl(text))
    base = BASE14.get(key)
    if base and not needs_unicode(text):
        return {"base": BASE14_STYLES[base][(1 if bold else 0) + (2 if italic else 0)]}
    return {"file": str(font_file(font, bold, italic, is_rtl(text)))}


def add_text(page, at, text: str, *, size=12, color=(0, 0, 0), font=None, bold=False,
             italic=False, underline=False, opacity=1.0, angle=0.0, pivot=None,
             overlay=True, width=None) -> pymupdf.Rect:
    """Draw text whose unrotated top-left is `at` in viewer coordinates.
    `angle` turns it counter-clockwise on screen around `pivot` (default `at`)."""
    if not text:
        return pymupdf.Rect(at, at)
    if is_rtl(text):
        return _add_rtl(page, at, text, size, color, font, bold, italic, underline,
                        opacity, angle, pivot, overlay, width)
    return _add_ltr(page, at, text, size, color, font, bold, italic, underline,
                    opacity, angle, pivot, overlay)


def _add_ltr(page, at, text, size, color, font, bold, italic, underline, opacity, angle, pivot, overlay):
    spec = _spec(font, bold, italic, text)
    path = spec.get("file")
    face = pymupdf.Font(fontfile=path) if path else pymupdf.Font(spec["base"])
    ascent = face.ascender or ASCENT_FALLBACK
    lines = text.split("\n")
    line_w = [face.text_length(line, size) for line in lines]
    leading = size * 1.2
    x, y = float(at[0]), float(at[1])
    box = pymupdf.Rect(x, y, x + max(line_w), y + leading * len(lines) + size * 0.1)
    centre = pymupdf.Point(pivot) if pivot is not None else pymupdf.Point(x, y)
    total = angle + page.rotation
    turn = pymupdf.Matrix(-angle)

    def to_native(px, py):
        return native_point(page, ((pymupdf.Point(px, py) - centre) * turn) + centre)

    shape = page.new_shape()
    kwargs = {"fontname": "F" + Path(path).stem if path else spec["base"]}
    if path:
        kwargs["fontfile"] = path
    for index, line in enumerate(lines):
        base_y = y + ascent * size + leading * index
        start = to_native(x, base_y)
        morph = (start, pymupdf.Matrix(total)) if total % 360 else None
        shape.insert_text(start, line, fontsize=size, color=color, fill=color,
                          fill_opacity=opacity, stroke_opacity=opacity, morph=morph,
                          rotate=0, border_width=0, render_mode=0, **kwargs)
        if underline:
            drop = base_y + size * 0.12
            shape.draw_line(to_native(x, drop), to_native(x + line_w[index], drop))
            shape.finish(color=color, width=max(size / 16, 0.5), stroke_opacity=opacity)
    shape.commit(overlay=overlay)
    return box


def _add_rtl(page, at, text, size, color, font, bold, italic, underline, opacity, angle, pivot, overlay, width):
    text_w, text_h, _ = measure(text, size, font, bold, italic)
    box_w = width or text_w * 1.08 + size * 0.8
    box = pymupdf.Rect(at[0], at[1], at[0] + box_w, at[1] + text_h + size * 0.5)
    total = (angle + page.rotation) % 360
    if total == 0:
        _html(page, box, text, size, color, font, bold, italic, underline, opacity, 0, overlay, "left", 1.0)
    else:
        _add_rtl_raster(page, box, text, size, color, font, bold, italic, underline,
                        opacity, angle, pivot, overlay)
    return box


def _html(page, rect, text, size, color, font, bold, italic, underline, opacity, rotate,
          overlay, align, scale_low, wrap=False) -> tuple[float, float]:
    key = family_key(font, is_rtl(text))
    rtl = base_is_rtl(text)
    css, archive = _css(key, size, color, underline, align, rtl, wrap)
    body = html.escape(text).replace("\n", "<br>")
    if bold:
        body = f"<b>{body}</b>"
    if italic:
        body = f"<i>{body}</i>"
    return page.insert_htmlbox(rect, body, css=css, archive=archive, scale_low=scale_low,
                               opacity=opacity, rotate=rotate, overlay=overlay)


def _css(key, size, color, underline, align, rtl, wrap):
    names = FAMILIES[key]
    faces = "".join(
        f"@font-face{{font-family:fp;font-weight:{w};font-style:{s};src:url({n}.ttf);}}"
        for n, w, s in ((names[0], "normal", "normal"), (names[1], "bold", "normal"),
                        (names[2], "normal", "italic"), (names[3], "bold", "italic"))
    )
    # mupdf mirrors text-align for direction:rtl, so "left" on screen needs "right" in CSS
    css_align = {"left": "right", "right": "left"}.get(align, align) if rtl else align
    decor = "underline" if underline else "none"
    direction = "rtl" if rtl else "ltr"
    body = (f"body{{font-family:fp;font-size:{size}pt;color:{css_color(color)};direction:{direction};"
            f"text-align:{css_align};margin:0;padding:0;text-decoration:{decor};line-height:1.2;}}")
    return faces + body, pymupdf.Archive(str(FONTS_DIR))


def _add_rtl_raster(page, box, text, size, color, font, bold, italic, underline, opacity, angle, pivot, overlay):
    from PIL import Image

    scale = 4
    tmp = pymupdf.open()
    sheet = tmp.new_page(width=box.width, height=box.height)
    _html(sheet, sheet.rect, text, size, color, font, bold, italic, underline, 1.0, 0, True, "left", 1.0)
    pix = sheet.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=True)
    tmp.close()
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
    turned = img.rotate(angle + page.rotation, expand=True, resample=Image.BICUBIC)
    alpha = turned.getchannel("A").point(lambda a: int(a * opacity))
    turned.putalpha(alpha)
    out = io.BytesIO()
    turned.save(out, "PNG")
    centre = pymupdf.Point(pivot) if pivot is not None else box.tl
    w, h = turned.width / scale, turned.height / scale
    middle = (((box.tl + box.br) / 2 - centre) * pymupdf.Matrix(-angle)) + centre
    mid = native_point(page, middle)
    target = pymupdf.Rect(mid.x - w / 2, mid.y - h / 2, mid.x + w / 2, mid.y + h / 2)
    page.insert_image(target, stream=out.getvalue(), overlay=overlay)


def fit_text_in_rect(page, rect, text, *, size, color, font=None, bold=False, italic=False,
                     align="left", rtl=None) -> float:
    """Place text in rect, shrinking until it fits. Returns the scale used."""
    css_rtl = rtl if rtl is not None else is_rtl(text)
    family = family_key(font, css_rtl)
    css, archive = _css(family, size, color, False, align, css_rtl, True)
    body = html.escape(text).replace("\n", "<br>")
    if bold:
        body = f"<b>{body}</b>"
    if italic:
        body = f"<i>{body}</i>"
    _, scale = page.insert_htmlbox(native_rect(page, rect), body, css=css, archive=archive,
                                   scale_low=0, overlay=True)
    return scale

