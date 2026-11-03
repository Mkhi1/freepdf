"""Redact: remove text, picture pixels and line art under chosen areas for good."""
import re
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pymupdf

from ..core import Job, ToolError, require, result
from ..registry import tool
from . import _textfit as tf
from ._mk_io import open_doc, save_doc
from ._text_find import find_text

REDACT_IMAGE_PIXELS = 2
DEFAULT_FILL = (0, 0, 0)


def _areas(doc, items: list[dict]) -> dict[int, list[pymupdf.Rect]]:
    found: dict[int, list[pymupdf.Rect]] = {}
    for item in items:
        kind = item.get("type")
        if kind == "area":
            page_no = item.get("page")
            if not isinstance(page_no, int) or not 0 <= page_no < doc.page_count:
                raise ToolError("bad_args", f"A redaction area points at page {page_no}, "
                                            f"but this file has {doc.page_count} pages.")
            rect = tf.native_rect(doc[page_no], pymupdf.Rect(require(item, "rect")))
            found.setdefault(page_no, []).append(rect)
        elif kind == "search":
            _add_matches(doc, item, found)
        else:
            raise ToolError("bad_args", f'"{kind}" is not a redaction item. Use area or search.')
    return found


def _add_matches(doc, item: dict, found: dict) -> None:
    needle = str(require(item, "text"))
    pages = [item["page"]] if isinstance(item.get("page"), int) else range(doc.page_count)
    for page_no in pages:
        for box in find_text(doc[page_no], needle, bool(item.get("case_sensitive"))):
            found.setdefault(page_no, []).append(box + (-0.5, -0.5, 0.5, 0.5))


def _scrub_side_channels(page, rects) -> None:
    """Annotations over a redacted area can carry the same words, so they go too."""
    for annot in list(page.annots() or []):
        if annot.type[0] != pymupdf.PDF_ANNOT_REDACT and any(annot.rect.intersects(r) for r in rects):
            page.delete_annot(annot)


def _scrub_outline(doc, terms: list[str]) -> int:
    toc = doc.get_toc(simple=False)
    changed = 0
    for entry in toc:
        for term in terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            if pattern.search(entry[1]):
                entry[1] = pattern.sub("[redacted]", entry[1])
                changed += 1
    if changed:
        doc.set_toc(toc)
    return changed


def _clean_metadata(doc) -> None:
    doc.set_metadata({})
    doc.del_xml_metadata()
    doc.scrub(metadata=True, xml_metadata=True, attached_files=False, clean_pages=False,
              embedded_files=False, hidden_text=False, javascript=True, reset_fields=False,
              reset_responses=False, thumbnails=True, redactions=False)


@tool("redact")
def redact(job: Job, args: dict) -> dict:
    doc = open_doc(args)
    items = require(args, "items")
    if not items:
        raise ToolError("bad_args", "Mark at least one area or word to redact.")
    areas = _areas(doc, items)
    fill = tf.parse_color(args.get("fill"), DEFAULT_FILL)
    terms = [str(i["text"]) for i in items if i.get("type") == "search"]
    total = 0
    for step, (page_no, rects) in enumerate(sorted(areas.items())):
        job.progress(step / max(len(areas), 1), f"Redacting page {page_no + 1}")
        page = doc[page_no]
        for rect in rects:
            page.add_redact_annot(rect, fill=fill)
        _scrub_side_channels(page, rects)
        page.apply_redactions(images=REDACT_IMAGE_PIXELS, graphics=1, text=0)
        total += len(rects)
    outline = _scrub_outline(doc, terms)
    if args.get("clean_metadata"):
        _clean_metadata(doc)
    out = save_doc(doc, args, "redacted", garbage=4, clean=True)
    return result([out], areas=total, pages=len(areas), outline_entries_changed=outline,
                  metadata_cleared=bool(args.get("clean_metadata")))
