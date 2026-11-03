"""Shared helpers for the PDF tools: opening files, saving, bookmarks."""
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pymupdf

from ..core import ToolError

pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)


def open_pdf(path, password: str | None = None) -> pymupdf.Document:
    """Open a PDF, unlocking it with password when it needs one."""
    name = getattr(path, "name", str(path))
    try:
        doc = pymupdf.open(str(path))
    except Exception as err:
        raise ToolError("not_a_pdf", f"{name} is not a PDF, or it is damaged. Try Repair a PDF.") from err
    if not doc.is_pdf:
        doc.close()
        raise ToolError("not_a_pdf", f"{name} is not a PDF file.")
    if doc.needs_pass and not doc.authenticate(password or ""):
        doc.close()
        message = "Wrong password. Check it and try again." if password else f"{name} needs a password to open."
        raise ToolError("wrong_password", message)
    return doc


def has_encryption(doc: pymupdf.Document) -> bool:
    """True for password-protected files and for ones that only carry owner restrictions."""
    return bool(doc.is_encrypted or doc.needs_pass or doc.xref_get_key(-1, "Encrypt")[0] != "null")


def save_pdf(doc: pymupdf.Document, path, **options) -> None:
    settings = {"garbage": 3, "deflate": True, **options}
    doc.save(str(path), **settings)


def check_pages(pages, count: int) -> list[int]:
    """Validate a 0-based page list from args. None means every page."""
    if pages is None:
        return list(range(count))
    try:
        chosen = [int(p) for p in pages]
    except (TypeError, ValueError) as err:
        raise ToolError("bad_args", "Pages must be a list of page numbers.") from err
    if not chosen:
        raise ToolError("bad_args", "Pick at least one page.")
    bad = [p for p in chosen if p < 0 or p >= count]
    if bad:
        raise ToolError("bad_args", f"Page {bad[0] + 1} is outside this file, which has {count} pages.")
    return chosen


def remap_toc(toc: list, page_map: dict[int, int], offset: int = 0) -> list:
    """Keep bookmarks whose page is in page_map (old 0-based -> new 0-based).

    Levels are repaired so the outline stays valid after entries are dropped.
    """
    kept = []
    previous_level = 0
    for entry in toc:
        level, title, page = entry[0], entry[1], entry[2]
        if page >= 1 and (page - 1) not in page_map:
            continue
        new_page = page_map[page - 1] + 1 + offset if page >= 1 else page
        level = min(max(level, 1), previous_level + 1)
        kept.append([level, title, new_page])
        previous_level = level
    return kept


def set_toc_safely(doc: pymupdf.Document, toc: list) -> None:
    if not toc:
        return
    try:
        doc.set_toc(toc)
    except Exception:
        pass
