"""PDF to Excel: real tables become cells (with merges and numeric values), everything else becomes rows."""
import re
import shutil
from collections import defaultdict
from pathlib import Path

import pymupdf
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

from ..convert_util import open_pdf, scratch_dir
from ..core import Job, ToolError, output_path, require, result
from ..registry import tool
from .docx_text import is_mostly_arabic
from .pdf_ocr import ocr_input
from .rtl_text import logical_line, page_text

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")
NUMBER = re.compile(r"^[-+]?\(?\$?€?£?\s?\d{1,3}(,\d{3})+(\.\d+)?\)?%?$|^[-+]?\(?\$?€?£?\s?\d+(\.\d+)?\)?%?$")
GAP_FACTOR = 1.5  # a horizontal gap wider than this many line heights starts a new column
THIN = Side(style="thin", color="999999")


def to_value(text: str):
    """Numbers become real numbers; ids with leading zeros and long digit runs stay text."""
    clean = ILLEGAL_CHARACTERS_RE.sub("", text).strip()
    raw = clean.translate(ARABIC_DIGITS)
    if not raw or not NUMBER.match(raw) or len(re.sub(r"\D", "", raw)) > 15:
        return clean
    digits = re.sub(r"[^\d.,()%+-]", "", raw)
    if re.match(r"^[-+]?0\d", digits) and "." not in digits:
        return clean
    negative = digits.startswith("-") or digits.startswith("(")
    number = float(re.sub(r"[^\d.]", "", digits.replace(",", "")) or "nan")
    number = -number if negative else number
    if digits.endswith("%"):
        return number / 100
    return int(number) if number.is_integer() and "." not in digits else number


def put(sheet, row: int, column: int, text: str):
    """Write PDF text to a cell. A line starting with = stays text instead of becoming a formula."""
    target = sheet.cell(row=row, column=column, value=to_value(text))
    if target.data_type == "f":
        target.data_type = "s"
    return target


def _edges(values: list[float], tolerance: float = 1.5) -> list[float]:
    merged: list[float] = []
    for value in sorted(values):
        if merged and value - merged[-1] <= tolerance:
            continue
        merged = [*merged, value]
    return merged


def _index(edges: list[float], value: float) -> int:
    return min(range(len(edges)), key=lambda i: abs(edges[i] - value))


def table_grid(page: pymupdf.Page, table) -> list[dict]:
    """Cells of a found table as {row, col, rows, cols, text}, with merged cells spanning their area."""
    cells = [c for c in table.cells if c]
    xs = _edges([c[0] for c in cells] + [c[2] for c in cells])
    ys = _edges([c[1] for c in cells] + [c[3] for c in cells])
    grid = []
    for x0, y0, x1, y1 in cells:
        col0, col1 = _index(xs, x0), _index(xs, x1)
        row0, row1 = _index(ys, y0), _index(ys, y1)
        text = " ".join(page_text(page, pymupdf.Rect(x0, y0, x1, y1) + (-0.5, -0.5, 0.5, 0.5)).split())
        grid.append({"row": row0, "col": col0, "rows": max(row1 - row0, 1), "cols": max(col1 - col0, 1), "text": text})
    return grid


def _plausible(table) -> bool:
    rows = table.extract()
    wide = [r for r in rows if sum(1 for c in r if c and c.strip()) >= 2]
    return len(rows) >= 3 and table.col_count >= 2 and len(wide) >= 0.6 * len(rows)


def find_page_tables(page: pymupdf.Page) -> list:
    tables = [t for t in page.find_tables().tables if t.row_count >= 1 and t.col_count >= 1 and t.cells]
    if tables:
        return tables
    guess = page.find_tables(strategy="text").tables
    return [t for t in guess if t.cells and _plausible(t)]


def text_rows(page: pymupdf.Page, skip: list[pymupdf.Rect], rtl: bool) -> list[tuple[float, list[str]]]:
    """Text lines outside tables as (top, cells), splitting a line into cells at wide gaps."""
    lines: dict[tuple[int, int], list[tuple]] = defaultdict(list)
    for x0, y0, x1, y1, text, block, line, _ in page.get_text("words"):
        lines[(block, line)].append((x0, y0, x1, y1, text))
    rows = []
    for words in lines.values():
        rect = pymupdf.Rect(min(w[0] for w in words), min(w[1] for w in words), max(w[2] for w in words), max(w[3] for w in words))
        if not any(rect.intersects(area) and (rect & area).get_area() > 0.5 * rect.get_area() for area in skip):
            rows.append((rect.y0, _split_line(words, rtl)))
    return sorted(rows, key=lambda r: r[0])


def _split_line(words: list[tuple], rtl: bool) -> list[str]:
    """Cells of one line in reading order, from its (x0, y0, x1, y1, text) words."""
    ordered = sorted(words, key=lambda w: w[0])
    groups = [[ordered[0]]]
    for word in ordered[1:]:
        if word[0] - groups[-1][-1][2] > GAP_FACTOR * max(word[3] - word[1], 1.0):
            groups = [*groups, [word]]
        else:
            groups = [*groups[:-1], [*groups[-1], word]]
    cells = [logical_line([(w[0], w[4]) for w in group]) for group in groups]
    return cells[::-1] if rtl else cells


def write_grid(sheet, start_row: int, grid: list[dict], rtl: bool) -> int:
    width = max(cell["col"] + cell["cols"] for cell in grid)
    last = start_row
    for cell in grid:
        row = start_row + cell["row"]
        col = width - cell["col"] - cell["cols"] + 1 if rtl else 1 + cell["col"]  # an RTL sheet starts at its right edge
        target = put(sheet, row, col, cell["text"])
        target.alignment = Alignment(wrap_text=True, vertical="top")
        target.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
        if cell["rows"] > 1 or cell["cols"] > 1:
            sheet.merge_cells(start_row=row, start_column=col, end_row=row + cell["rows"] - 1, end_column=col + cell["cols"] - 1)
        last = max(last, row + cell["rows"] - 1)
    return last


def write_page(sheet, start_row: int, page: pymupdf.Page, rtl: bool) -> int:
    """Append one PDF page to a sheet in reading order; return the next free row."""
    tables = find_page_tables(page)
    items = [(t.bbox[1], "table", t) for t in tables]
    items += [(top, "text", cells) for top, cells in text_rows(page, [pymupdf.Rect(t.bbox) for t in tables], rtl)]
    row = start_row
    for _, kind, payload in sorted(items, key=lambda i: i[0]):
        if kind == "table":
            row = write_grid(sheet, row, table_grid(page, payload), rtl) + 2
        else:
            for offset, text in enumerate(payload):
                put(sheet, row, 1 + offset, text)
            row += 1
    return row


def _fit_columns(sheet) -> None:
    widths: dict[int, int] = {}
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value is not None:
                widths[cell.column] = max(widths.get(cell.column, 8), min(len(str(cell.value)) + 2, 60))
    for column, width in widths.items():
        sheet.column_dimensions[get_column_letter(column)].width = width


def build_workbook(job: Job, doc: pymupdf.Document, one_sheet: bool) -> Workbook:
    book = Workbook()
    book.remove(book.active)
    shared = book.create_sheet("Sheet1") if one_sheet else None
    row = 1
    arabic = any(is_mostly_arabic(doc[index].get_text()[:2000]) for index in range(doc.page_count))
    for index in range(doc.page_count):
        job.progress(0.1 + 0.8 * index / doc.page_count, f"Page {index + 1} of {doc.page_count}")
        page = doc[index]
        sheet = shared or book.create_sheet(f"Page {index + 1}")
        row = write_page(sheet, row if one_sheet else 1, page, arabic) + (1 if one_sheet else 0)
    for sheet in book.worksheets:
        _fit_columns(sheet)
        if arabic:
            sheet.sheet_view.rightToLeft = True
    return book


@tool("pdf_to_excel")
def pdf_to_excel(job: Job, args: dict) -> dict:
    source = Path(require(args, "file"))
    doc = open_pdf(str(source), args.get("password"))
    work_dir = scratch_dir()
    try:
        prepared = ocr_input(job, source, args, work_dir)
        if prepared != source:
            doc.close()
            doc = open_pdf(str(prepared))
        book = build_workbook(job, doc, bool(args.get("one_sheet")))
        target = output_path(source, "", ".xlsx", args.get("out_dir"))
        book.save(str(target))
        tables = sum(len(find_page_tables(doc[i])) for i in range(min(doc.page_count, 50)))
    finally:
        doc.close()
        shutil.rmtree(work_dir, ignore_errors=True)
    if not target.exists():
        raise ToolError("tool_failed", "The spreadsheet could not be created.")
    return result([target], sheets=len(book.worksheets), tables=tables)
