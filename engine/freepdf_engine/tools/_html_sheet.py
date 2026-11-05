"""Excel (.xlsx, .xlsm, .csv) to HTML for printing without Office: one table per sheet, with fonts, fills and merges."""
import csv
import datetime as dt
from pathlib import Path

from ._html_common import document, esc, hex_color, page_css, style, text_dir

MAX_ROWS = 5000
MAX_COLS = 60
CSS = (".sheet{break-after:page}.sheet:last-child{break-after:auto}"
       "h2{font-size:11pt;margin:0 0 6pt;color:#444}"
       "table.grid{font-size:10pt}table.grid td{border:1px solid #bfbfbf;padding:1.5pt 4pt;white-space:nowrap;vertical-align:bottom}")


def _format_value(value, number_format: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M") if (value.hour or value.minute) else value.strftime("%Y-%m-%d")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float):
        if "%" in (number_format or ""):
            decimals = number_format.split(".")[1].count("0") if "." in number_format else 0
            return f"{value * 100:.{decimals}f}%"
        if "0.00" in (number_format or ""):
            return f"{value:,.2f}" if "," in number_format else f"{value:.2f}"
        return f"{value:.10g}"
    if isinstance(value, int) and "," in (number_format or ""):
        return f"{value:,}"
    return str(value)


def _cell_css(cell) -> str:
    font, fill, align = cell.font, cell.fill, cell.alignment
    numeric = isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
    background = hex_color(fill.fgColor.rgb) if fill is not None and fill.fill_type == "solid" and fill.fgColor.type == "rgb" else None
    color = hex_color(font.color.rgb) if font is not None and font.color is not None and font.color.type == "rgb" else None
    return style(
        font_weight="bold" if font is not None and font.b else None,
        font_style="italic" if font is not None and font.i else None,
        text_decoration="underline" if font is not None and font.u else None,
        color=color if color not in ("#000000",) else None,
        background=background,
        text_align=(align.horizontal if align is not None and align.horizontal in ("left", "center", "right") else ("right" if numeric else None)),
        white_space="normal" if align is not None and align.wrap_text else None,
    )


def _merge_map(sheet) -> tuple[dict, set]:
    starts, covered = {}, set()
    for merged in sheet.merged_cells.ranges:
        starts[(merged.min_row, merged.min_col)] = (merged.max_row - merged.min_row + 1, merged.max_col - merged.min_col + 1)
        for row in range(merged.min_row, merged.max_row + 1):
            for col in range(merged.min_col, merged.max_col + 1):
                if (row, col) != (merged.min_row, merged.min_col):
                    covered.add((row, col))
    return starts, covered


def _sheet_html(sheet) -> str:
    from openpyxl.utils import get_column_letter
    rows, cols = min(sheet.max_row, MAX_ROWS), min(sheet.max_column, MAX_COLS)
    starts, covered = _merge_map(sheet)
    widths = []
    for col in range(1, cols + 1):
        dim = sheet.column_dimensions.get(get_column_letter(col))
        widths.append(f'<col style="width:{(dim.width if dim is not None and dim.width else 8.43) * 7 + 5:.0f}px">')
    body = []
    for row in sheet.iter_rows(min_row=1, max_row=rows, max_col=cols):
        cells = []
        for cell in row:
            key = (cell.row, cell.column)
            if key in covered:
                continue
            text = _format_value(cell.value, cell.number_format)
            span_rows, span_cols = starts.get(key, (1, 1))
            attrs = (f' rowspan="{span_rows}"' if span_rows > 1 else "") + (f' colspan="{span_cols}"' if span_cols > 1 else "")
            cells.append(f'<td dir="{text_dir(text)}"{attrs}{_cell_css(cell)}>{esc(text)}</td>')
        body.append(f"<tr>{''.join(cells)}</tr>")
    return f'<section class="sheet"><h2>{esc(sheet.title)}</h2><table class="grid">{"".join(widths)}{"".join(body)}</table></section>'


def _csv_html(src: Path) -> str:
    text = src.read_bytes().decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(text.splitlines()))[:MAX_ROWS]
    body = "".join("<tr>" + "".join(f'<td dir="{text_dir(v)}">{esc(v)}</td>' for v in row[:MAX_COLS]) + "</tr>" for row in rows)
    return f'<section class="sheet"><table class="grid">{body}</table></section>'


def sheet_to_html(src: Path) -> str:
    page = page_css(11.69, 8.27, (0.5, 0.5, 0.5, 0.5))  # landscape A4 suits wide sheets
    if src.suffix.lower() == ".csv":
        return document(_csv_html(src), page + CSS)
    from openpyxl import load_workbook
    book = load_workbook(str(src), data_only=True, read_only=False)
    try:
        sheets = [s for s in book.worksheets if s.sheet_state == "visible" and s.max_row and (s.max_row > 1 or s["A1"].value is not None)]
        body = "".join(_sheet_html(sheet) for sheet in sheets) or '<section class="sheet"><p>This workbook has no data.</p></section>'
    finally:
        book.close()
    return document(body, page + CSS)
