"""Word (.docx) to HTML for printing without Office: paragraphs, runs, lists, tables, pictures and page setup."""
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from ._html_common import data_uri, document, esc, hex_color, page_css, style, text_dir

EMU_PER_PX = 9525
ALIGN = {0: "left", 1: "center", 2: "right", 3: "justify"}
HEADINGS = {"Title": ("h1", 26), "Subtitle": ("h2", 15), "Heading 1": ("h1", 16), "Heading 2": ("h2", 13),
            "Heading 3": ("h3", 12), "Heading 4": ("h4", 11), "Heading 5": ("h5", 11), "Heading 6": ("h6", 11)}
HEADING_COLOR = "#2f5496"


def _pt(length) -> str | None:
    return f"{length.pt:.1f}pt" if length is not None else None


def _inherited(paragraph: Paragraph, getter):
    """First value set on the paragraph, then up its style chain."""
    value = getter(paragraph.paragraph_format)
    style_obj = paragraph.style
    while value is None and style_obj is not None:
        value = getter(style_obj.paragraph_format)
        style_obj = style_obj.base_style
    return value


def _run_images(run, part) -> str:
    out = []
    for drawing in run._element.iter(qn("w:drawing")):
        extent = next(drawing.iter(qn("wp:extent")), None)
        blip = next(drawing.iter(qn("a:blip")), None)
        rid = blip.get(qn("r:embed")) if blip is not None else None
        image_part = part.related_parts.get(rid) if rid else None
        if image_part is None:
            continue
        width = int(extent.get("cx")) // EMU_PER_PX if extent is not None else None
        height = int(extent.get("cy")) // EMU_PER_PX if extent is not None else None
        src = data_uri(image_part.blob, Path(str(image_part.partname)).suffix)
        out.append(f'<img src="{src}"{style(width=f"{width}px" if width else None, height=f"{height}px" if height else None)}>')
    return "".join(out)


def _run_html(run, part) -> str:
    pieces = []
    for child in run._element:
        tag = child.tag
        if tag == qn("w:t"):
            pieces.append(esc(child.text or ""))
        elif tag == qn("w:tab"):
            pieces.append("&emsp;")
        elif tag == qn("w:br"):
            pieces.append('<span class="pb"></span>' if child.get(qn("w:type")) == "page" else "<br>")
    text = "".join(pieces)
    images = _run_images(run, part)
    if not text and not images:
        return ""
    font = run.font
    css = style(
        font_weight="bold" if run.bold else None,
        font_style="italic" if run.italic else None,
        text_decoration="underline" if run.underline else ("line-through" if font.strike else None),
        font_size=_pt(font.size),
        color=hex_color(font.color.rgb) if font.color is not None and font.color.type is not None else None,
        font_family=f"'{font.name}'" if font.name else None,
        background="yellow" if font.highlight_color is not None else None,
        vertical_align="super" if font.superscript else ("sub" if font.subscript else None),
    )
    return f"<span{css}>{text}</span>{images}" if text else images


def _is_list(paragraph: Paragraph) -> bool:
    ppr = paragraph._p.pPr
    return (ppr is not None and ppr.numPr is not None) or paragraph.style.name.startswith("List")


def _paragraph_html(paragraph: Paragraph, part, numbering: dict) -> str:
    runs = [run for item in paragraph.iter_inner_content() for run in (item.runs if hasattr(item, "runs") else [item])]
    content = "".join(_run_html(run, part) for run in runs)
    name = paragraph.style.name if paragraph.style is not None else ""
    tag, size = HEADINGS.get(name, ("p", None))
    ppr = paragraph._p.pPr
    rtl = ppr is not None and ppr.find(qn("w:bidi")) is not None
    direction = "rtl" if rtl else text_dir(paragraph.text)
    align = _inherited(paragraph, lambda f: f.alignment)
    before = _inherited(paragraph, lambda f: f.space_before)
    after = _inherited(paragraph, lambda f: f.space_after)
    indent = _inherited(paragraph, lambda f: f.left_indent)
    marker = ""
    if _is_list(paragraph) and tag == "p":
        numbered = "Number" in name
        numbering["n"] = numbering.get("n", 0) + 1 if numbered else 0
        marker = f'<span class="mk">{numbering["n"]}.</span>' if numbered else '<span class="mk">•</span>'
    else:
        numbering["n"] = 0
    css = style(
        text_align=ALIGN.get(int(align)) if align is not None else ("right" if direction == "rtl" else None),
        margin_top=_pt(before), margin_bottom=_pt(after) or "8pt",
        padding_inline_start="0.25in" if marker else (_pt(indent) if indent else None),
        font_size=f"{size}pt" if size else None, color=HEADING_COLOR if size else None,
    )
    return f'<{tag} dir="{direction}"{css}>{marker}{content or "&nbsp;"}</{tag}>'


def _cell_fill(tc) -> str | None:
    tcpr = tc.tcPr
    shd = tcpr.find(qn("w:shd")) if tcpr is not None else None
    fill = shd.get(qn("w:fill")) if shd is not None else None
    return hex_color(fill) if fill and fill != "auto" else None


def _rowspan(rows, row_index: int, col: int) -> int:
    span = 1
    for tr in rows[row_index + 1:]:
        cell = _cell_at(tr, col)
        if cell is None or cell.vMerge != "continue":
            break
        span += 1
    return span


def _cell_at(tr, col: int):
    position = 0
    for tc in tr.tc_lst:
        if position == col:
            return tc
        position += tc.grid_span
    return None


def _table_html(table: Table, part, numbering: dict) -> str:
    style_name = table.style.name if table.style is not None else ""
    tblpr = table._tbl.tblPr
    bordered = "Grid" in style_name or (tblpr is not None and tblpr.find(qn("w:tblBorders")) is not None)
    border = "1px solid #000" if bordered else None
    rows = list(table._tbl.tr_lst)
    body = []
    for r, tr in enumerate(rows):
        cells, col = [], 0
        for tc in tr.tc_lst:
            span = tc.grid_span
            if tc.vMerge != "continue":
                inner = "".join(_block_html(child, table._parent, part, numbering) for child in tc.iterchildren()
                                if child.tag in (qn("w:p"), qn("w:tbl")))
                attrs = (f' colspan="{span}"' if span > 1 else "")
                rowspan = _rowspan(rows, r, col) if tc.vMerge == "restart" else 1
                attrs += f' rowspan="{rowspan}"' if rowspan > 1 else ""
                cells.append(f"<td{attrs}{style(border=border, background=_cell_fill(tc))}>{inner}</td>")
            col += span
        body.append(f"<tr>{''.join(cells)}</tr>")
    return f'<table class="tb">{"".join(body)}</table>'


def _block_html(element, parent, part, numbering: dict) -> str:
    if element.tag == qn("w:p"):
        return _paragraph_html(Paragraph(element, parent), part, numbering)
    if element.tag == qn("w:tbl"):
        return _table_html(Table(element, parent), part, numbering)
    return ""


def _default_font(doc) -> tuple[str, str]:
    font = doc.styles["Normal"].font
    return (f"'{font.name}'," if font.name else ""), (f"{font.size.pt:.1f}pt" if font.size else "11pt")


def _columns_css(section) -> str:
    """Newspaper columns set in the section (Layout > Columns)."""
    cols = section._sectPr.find(qn("w:cols"))
    count = int(cols.get(qn("w:num")) or 1) if cols is not None else 1
    if count < 2:
        return ""
    gap_pt = int(cols.get(qn("w:space")) or 720) / 20  # twentieths of a point
    return f".flow{{column-count:{count};column-gap:{gap_pt:.0f}pt}}"


def docx_to_html(src: Path) -> str:
    doc = Document(str(src))
    section = doc.sections[0]
    inches = lambda value, fallback: value.inches if value is not None else fallback  # noqa: E731
    page = page_css(inches(section.page_width, 8.5), inches(section.page_height, 11),
                    (inches(section.top_margin, 1), inches(section.right_margin, 1),
                     inches(section.bottom_margin, 1), inches(section.left_margin, 1)))
    family, size = _default_font(doc)
    css = (f"{page}body{{font-family:{family}Calibri,Arial,sans-serif;font-size:{size};line-height:1.15}}"
           "h1,h2,h3,h4,h5,h6{font-weight:600;margin:12pt 0 4pt}.tb{margin:4pt 0 8pt;width:auto}"
           ".tb td{padding:2pt 5pt;vertical-align:top}.tb p{margin:0!important}"
           ".mk{display:inline-block;min-width:0.25in;margin-inline-start:-0.25in}"
           ".pb{display:block;break-after:page}" + _columns_css(section))
    numbering: dict = {}
    body = "".join(_block_html(child, doc._body, doc.part, numbering) for child in doc.element.body.iterchildren())
    return document(f'<div class="flow">{body}</div>', css)
