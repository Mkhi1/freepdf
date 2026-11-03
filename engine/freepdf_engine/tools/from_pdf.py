"""PDF to images and text. Word, PowerPoint and Excel exports live in pdf_word, pdf_ppt and pdf_excel."""
from pathlib import Path

import pymupdf

from ..convert_util import open_pdf, zip_files
from ..core import Job, ToolError, output_path, parse_ranges, require, result
from ..registry import tool
from .rtl_text import page_text
from . import pdf_excel, pdf_ppt, pdf_word  # noqa: F401  (registers their tools)

MIN_EXTRACT_SIDE = 8  # skip decorative 1-pixel spacer images


def pick_pages(spec, page_count: int) -> list[int]:
    if spec in (None, "", []):
        return list(range(page_count))
    if isinstance(spec, str):
        return parse_ranges(spec, page_count)
    pages = sorted({int(p) for p in spec})
    if not pages or pages[0] < 0 or pages[-1] >= page_count:
        raise ToolError("bad_args", f"Pages are outside this file, which has {page_count} pages.")
    return pages


def _finish(job: Job, source: Path, files: list[Path], args: dict, label: str) -> list[Path]:
    if args.get("zip") and len(files) > 1:
        archive = zip_files(files, output_path(source, label, ".zip", args.get("out_dir")))
        for path in files:
            path.unlink(missing_ok=True)
        return [archive]
    return files


def _render_pages(job: Job, doc: pymupdf.Document, source: Path, pages: list[int], args: dict) -> list[Path]:
    fmt = str(args.get("format", "jpg")).lower().replace("jpeg", "jpg")
    if fmt not in ("jpg", "png"):
        raise ToolError("bad_args", "Format must be jpg or png.")
    dpi = int(args.get("dpi") or 150)
    quality = int(args.get("quality") or 90)
    if not 36 <= dpi <= 1200 or not 1 <= quality <= 100:
        raise ToolError("bad_args", "Resolution must be 36 to 1200 dpi and quality 1 to 100.")
    files: list[Path] = []
    for done, index in enumerate(pages):
        job.progress(done / len(pages), f"Page {index + 1} of {doc.page_count}")
        pix = doc[index].get_pixmap(dpi=dpi, alpha=False)
        target = output_path(source, f"page {index + 1}", f".{fmt}", args.get("out_dir"))
        target.write_bytes(pix.tobytes("jpg", jpg_quality=quality) if fmt == "jpg" else pix.tobytes("png"))
        files = [*files, target]
    return files


def _extract_images(job: Job, doc: pymupdf.Document, source: Path, pages: list[int], args: dict) -> list[Path]:
    files: list[Path] = []
    seen: set[int] = set()
    for done, index in enumerate(pages):
        job.progress(done / len(pages), f"Page {index + 1} of {doc.page_count}")
        for entry in doc[index].get_images(full=True):
            xref = entry[0]
            if xref in seen:
                continue
            seen.add(xref)
            info = doc.extract_image(xref)
            if not info or min(info.get("width", 0), info.get("height", 0)) < MIN_EXTRACT_SIDE:
                continue
            label = f"page {index + 1} image {len(files) + 1}"
            target = output_path(source, label, f".{info['ext']}", args.get("out_dir"))
            target.write_bytes(info["image"])  # the original embedded bytes, not re-encoded
            files = [*files, target]
    if not files:
        raise ToolError("tool_failed", "This PDF has no embedded pictures to extract. Use the page mode to turn pages into images.")
    return files


@tool("pdf_to_images")
def pdf_to_images(job: Job, args: dict) -> dict:
    source = Path(require(args, "file"))
    mode = str(args.get("mode", "pages"))
    if mode not in ("pages", "extract"):
        raise ToolError("bad_args", "Mode must be pages or extract.")
    doc = open_pdf(str(source), args.get("password"))
    try:
        pages = pick_pages(args.get("pages"), doc.page_count)
        work = _render_pages if mode == "pages" else _extract_images
        files = work(job, doc, source, pages, args)
    finally:
        doc.close()
    outputs = _finish(job, source, files, args, "images")
    return result(outputs, images=len(files), mode=mode)


@tool("pdf_to_text")
def pdf_to_text(job: Job, args: dict) -> dict:
    source = Path(require(args, "file"))
    doc = open_pdf(str(source), args.get("password"))
    try:
        pages = pick_pages(args.get("pages"), doc.page_count)
        chunks: list[str] = []
        for done, index in enumerate(pages):
            job.progress(done / len(pages), f"Page {index + 1} of {doc.page_count}")
            chunks = [*chunks, page_text(doc[index]).rstrip()]
    finally:
        doc.close()
    text = "\n\n".join(chunks).strip()
    target = output_path(source, "", ".txt", args.get("out_dir"))
    target.write_text(text + "\n", encoding="utf-8")
    return result([target], characters=len(text), pages=len(pages), has_text=bool(text))
