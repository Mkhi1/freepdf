"""PowerPoint (.pptx) to HTML for printing without Office: one page per slide, shapes placed where they sit."""
import re
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Emu

from ._html_common import data_uri, document, esc, hex_color, style, text_dir

EMU_PER_PT = 12700
ALIGN = {1: "left", 2: "center", 3: "right", 4: "justify"}
ANCHOR = {1: "flex-start", 3: "center", 4: "flex-end"}  # top, middle, bottom
DEFAULT_SIZE_PT = 18


def _pt(emu) -> float:
    return (emu or 0) / EMU_PER_PT


def _box(shape, dx: float = 0, dy: float = 0) -> dict:
    return {"left": f"{_pt(shape.left) + dx:.2f}pt", "top": f"{_pt(shape.top) + dy:.2f}pt",
            "width": f"{_pt(shape.width):.2f}pt", "height": f"{_pt(shape.height):.2f}pt"}


def _color_of(fill_or_font) -> str | None:
    try:
        return hex_color(fill_or_font.color.rgb)
    except (AttributeError, TypeError, ValueError):
        return None


def _fill(shape) -> str | None:
    try:
        fill = shape.fill
        return hex_color(fill.fore_color.rgb) if fill.type == 1 else None  # MSO_FILL.SOLID
    except (AttributeError, TypeError, ValueError):
        return None


def _line(shape) -> str | None:
    try:
        line = shape.line
        color = hex_color(line.color.rgb) if line.fill.type == 1 else None
        return f"{max(_pt(line.width), 0.75):.2f}pt solid {color}" if color else None
    except (AttributeError, TypeError, ValueError):
        return None


def _family(name: str | None) -> str:
    """CSS font stack. PDF font names like 'Arial-ItalicMT' become 'Arial', and a sans fallback keeps Times away."""
    if not name:
        return "Calibri,Arial,sans-serif"
    base = re.sub(r"(PSMT|MT|PS)$", "", re.split(r"[-,]", name)[0]).strip()
    names = dict.fromkeys(n for n in (name, base) if n)
    return ",".join(f"'{n}'" for n in names) + ",Arial,sans-serif"


def _run_html(run, fallback_pt: float) -> str:
    font = run.font
    lowered = (font.name or "").lower()
    css = style(
        font_size=f"{font.size.pt:.1f}pt" if font.size else f"{fallback_pt:.0f}pt",
        font_weight="bold" if font.bold or "bold" in lowered else None,
        font_style="italic" if font.italic or "italic" in lowered or "oblique" in lowered else None,
        text_decoration="underline" if font.underline else None,
        color=_color_of(font),
        font_family=_family(font.name),
    )
    return f"<span{css}>{esc(run.text).replace(chr(11), '<br>')}</span>"


def _paragraph_inner(paragraph, fallback_pt: float) -> str:
    """Runs and line breaks in document order; python-pptx's runs list skips the breaks."""
    runs = iter(paragraph.runs)
    parts = []
    for child in paragraph._p:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "r":
            parts.append(_run_html(next(runs), fallback_pt))
        elif tag == "br":
            parts.append("<br>")
        elif tag == "fld":
            parts.append(esc("".join(child.itertext())))
    return "".join(parts)


def _spacing(paragraph) -> dict:
    line = paragraph.line_spacing
    height = f"{line.pt:.2f}pt" if hasattr(line, "pt") else (f"{line * 1.2:.2f}" if isinstance(line, float) else None)
    return {"line_height": height,
            "margin_top": f"{paragraph.space_before.pt:.1f}pt" if paragraph.space_before is not None else None,
            "margin_bottom": f"{paragraph.space_after.pt:.1f}pt" if paragraph.space_after is not None else None}


def _frame_html(frame, fallback_pt: float) -> str:
    paragraphs = []
    for paragraph in frame.paragraphs:
        text = "".join(run.text for run in paragraph.runs)
        inner = _paragraph_inner(paragraph, fallback_pt) or "&nbsp;"
        align = ALIGN.get(int(paragraph.alignment)) if paragraph.alignment is not None else None
        bullet = paragraph.level > 0
        css = style(
            text_align=align or ("right" if text_dir(text) == "rtl" else None),
            padding_inline_start=f"{0.9 * paragraph.level:.1f}em" if bullet else None,
            **_spacing(paragraph),
        )
        prefix = "• " if bullet else ""
        paragraphs.append(f'<p dir="{text_dir(text)}"{css}>{prefix}{inner}</p>')
    return "".join(paragraphs)


def _insets(frame) -> str:
    def pt(value, default):
        return f"{_pt(value):.2f}pt" if value is not None else default
    return " ".join((pt(frame.margin_top, "3.6pt"), pt(frame.margin_right, "7.2pt"),
                     pt(frame.margin_bottom, "3.6pt"), pt(frame.margin_left, "7.2pt")))


def _fallback_size(shape) -> float:
    if shape.is_placeholder:
        kind = str(shape.placeholder_format.type)
        if "TITLE" in kind and "SUB" not in kind:
            return 40 if "CENTER" in kind else 36
        if "SUBTITLE" in kind:
            return 24
    return DEFAULT_SIZE_PT


def _table_html(shape) -> str:
    rows = []
    for row in shape.table.rows:
        cells = []
        for cell in row.cells:
            if cell.is_spanned:
                continue
            attrs = (f' colspan="{cell.span_width}"' if cell.span_width > 1 else "") + (f' rowspan="{cell.span_height}"' if cell.span_height > 1 else "")
            cells.append(f'<td{attrs}{style(background=_fill(cell))}>{_frame_html(cell.text_frame, 14)}</td>')
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f'<table class="st">{"".join(rows)}</table>'


def _shape_html(shape, dx: float = 0, dy: float = 0) -> str:
    if shape.left is None or shape.width is None:
        return ""
    box = _box(shape, dx, dy)
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        return "".join(_shape_html(child, dx, dy) for child in shape.shapes)
    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        image = shape.image
        return f'<img class="sh" src="{data_uri(image.blob, image.ext)}"{style(**box)}>'
    if getattr(shape, "has_table", False):
        return f'<div class="sh"{style(**box)}>{_table_html(shape)}</div>'
    rounded = "ellipse" in str(getattr(shape, "auto_shape_type", "") or "").lower() if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE else False
    look = {"background": _fill(shape), "border": _line(shape), "border_radius": "50%" if rounded else None}
    if not shape.has_text_frame:
        return f'<div class="sh"{style(**box, **look)}></div>'
    frame = shape.text_frame
    anchor = ANCHOR.get(int(frame.vertical_anchor)) if frame.vertical_anchor is not None else None
    inner = _frame_html(frame, _fallback_size(shape))
    wrap = None if frame.word_wrap is not False else "nowrap"
    css = style(**box, **look, justify_content=anchor or "flex-start", padding=_insets(frame), white_space=wrap)
    return f'<div class="sh tx"{css}>{inner}</div>'


def _background(slide) -> str | None:
    try:
        fill = slide.background.fill
        return hex_color(fill.fore_color.rgb) if fill.type == 1 else None
    except (AttributeError, TypeError, ValueError):
        return None


def _layout_shapes(slide) -> list:
    """Pictures and plain shapes from the layout and master, like logos and bars, drawn under the slide."""
    shapes = []
    for source in (slide.slide_layout.slide_master, slide.slide_layout):
        shapes.extend(s for s in source.shapes if not s.is_placeholder)
    return shapes


def slides_to_html(src: Path) -> str:
    deck = Presentation(str(src))
    width, height = _pt(deck.slide_width or Emu(9144000)), _pt(deck.slide_height or Emu(6858000))
    pages = []
    for slide in deck.slides:
        shapes = "".join(_shape_html(s) for s in [*_layout_shapes(slide), *slide.shapes])
        pages.append(f'<section class="slide"{style(background=_background(slide) or "#fff")}>{shapes}</section>')
    css = (f"@page{{size:{width:.2f}pt {height:.2f}pt;margin:0}}"
           f".slide{{position:relative;width:{width:.2f}pt;height:{height:.2f}pt;overflow:hidden;break-after:page}}"
           ".slide:last-child{break-after:auto}.sh{position:absolute;margin:0}"
           ".tx{display:flex;flex-direction:column;line-height:1.2;overflow:visible}"
           ".tx p{margin:0}.st{width:100%;height:100%;border-collapse:collapse;font-size:14pt}"
           ".st td{border:1px solid #fff;padding:3pt 6pt;background:#e8ecf4}")
    return document("".join(pages) or '<section class="slide"></section>', css)
