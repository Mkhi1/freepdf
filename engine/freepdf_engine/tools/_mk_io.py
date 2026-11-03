"""Opening and saving PDFs for the mark-up tools, with the shared error messages."""
import warnings
from pathlib import Path

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pymupdf

from ..core import ToolError, output_path, parse_ranges, require, require_file

pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)


def open_doc(args: dict, key: str = "file", password_key: str = "password") -> pymupdf.Document:
    path = require_file(require(args, key))
    try:
        doc = pymupdf.open(str(path))
    except Exception as err:
        raise ToolError("not_a_pdf", f"{path.name} could not be opened as a PDF. The file may be damaged.") from err
    if not doc.is_pdf:
        doc.close()
        raise ToolError("not_a_pdf", f"{path.name} is not a PDF file.")
    if doc.needs_pass and not doc.authenticate(args.get(password_key) or ""):
        doc.close()
        raise ToolError("wrong_password", f"{path.name} needs the right password to open it.")
    return doc


def save_doc(doc: pymupdf.Document, args: dict, label: str, key: str = "file", **save_args) -> Path:
    src = Path(args[key])
    out = output_path(src, label, ".pdf", args.get("out_dir"))
    options = {"garbage": 3, "deflate": True, "encryption": pymupdf.PDF_ENCRYPT_NONE, **save_args}
    doc.save(str(out), **options)
    doc.close()
    return out


def subset_fonts(doc: pymupdf.Document) -> None:
    try:
        doc.subset_fonts()
    except Exception:
        pass


def page_window(args: dict, page_count: int) -> list[int]:
    """0-based pages for from_page and to_page, which users enter 1-based and inclusive."""
    first = int(args.get("from_page") or 1)
    last = int(args.get("to_page") or page_count)
    if first < 1 or last > page_count or first > last:
        raise ToolError("bad_args", f"Choose pages between 1 and {page_count}; this file has {page_count} pages.")
    return list(range(first - 1, last))


def pages_from(args: dict, key: str, page_count: int) -> list[int]:
    """Pages from a 1-based range string such as "1-3,7", or every page when absent."""
    spec = args.get(key)
    return parse_ranges(spec, page_count) if spec else list(range(page_count))
