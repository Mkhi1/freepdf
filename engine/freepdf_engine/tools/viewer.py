"""Viewer tools: info, thumb, page_text, search. Kept light so the reader stays instant."""
import hashlib
import re
import tempfile
from pathlib import Path

from ..core import Job, ToolError, require, require_file, result
from ..registry import tool
from ._pdf_common import check_pages, has_encryption, open_pdf, pymupdf
from ._text_find import find_text, normal_text

THUMB_DIR = Path(tempfile.gettempdir()) / "freepdf-thumbs"
SCAN_SAMPLE_PAGES = 5
MIN_REAL_TEXT = 12
ARABIC_LETTER = re.compile("[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


def _open_for_viewer(args: dict):
    src = require_file(require(args, "file"))
    return src, open_pdf(src, args.get("password"))


@tool("info")
def info(job: Job, args: dict) -> dict:
    src = require_file(require(args, "file"))
    try:
        doc = open_pdf(src, args.get("password"))
    except ToolError as err:
        if err.code == "wrong_password" and not args.get("password"):
            return result([], pages=0, sizes=[], encrypted=True, needs_password=True, scanned=False,
                          title="", bytes=src.stat().st_size)
        raise
    with doc:
        sizes = [[round(p.rect.width, 2), round(p.rect.height, 2)] for p in doc]
        return result(
            [], pages=len(doc), sizes=sizes, encrypted=has_encryption(doc), needs_password=False,
            scanned=_looks_scanned(doc), title=(doc.metadata or {}).get("title") or "",
            bytes=src.stat().st_size,
        )


def _looks_scanned(doc) -> bool:
    """True when sampled pages carry images but almost no real text."""
    count = len(doc)
    if count == 0:
        return False
    step = max(count // SCAN_SAMPLE_PAGES, 1)
    sample = list(range(0, count, step))[:SCAN_SAMPLE_PAGES]
    scanned = 0
    for index in sample:
        page = doc[index]
        has_text = len(page.get_text("text").strip()) >= MIN_REAL_TEXT
        if not has_text and page.get_image_info():
            scanned += 1
    return scanned * 2 > len(sample)


def _thumb_key(src: Path, page: int, width: int) -> str:
    stamp = src.stat().st_mtime_ns
    raw = f"{src.resolve()}|{stamp}|{page}|{width}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


@tool("thumb")
def thumb(job: Job, args: dict) -> dict:
    src = require_file(require(args, "file"))
    page_number = int(require(args, "page"))
    width = int(args.get("width") or 160)
    if width < 16 or width > 4000:
        raise ToolError("bad_args", "Thumbnail width must be between 16 and 4000 pixels.")
    cached = THUMB_DIR / f"{_thumb_key(src, page_number, width)}.png"
    if cached.is_file():
        return result([], path=str(cached), cached=True)
    with open_pdf(src, args.get("password")) as doc:
        index = check_pages([page_number], len(doc))[0]
        page = doc[index]
        zoom = width / page.rect.width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        partial = cached.with_suffix(".tmp")
        partial.write_bytes(pix.tobytes("png"))
        partial.replace(cached)
    return result([], path=str(cached), cached=False)


def _is_rtl(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    rtl = sum(1 for c in letters if "֐" <= c <= "ࣿ" or "יִ" <= c <= "﻿")
    return rtl * 2 > len(letters)


@tool("page_text")
def page_text(job: Job, args: dict) -> dict:
    page_number = int(require(args, "page"))
    _, doc = _open_for_viewer(args)
    with doc:
        index = check_pages([page_number], len(doc))[0]
        text = doc[index].get_text("text", sort=True)
    return result([], text=text, rtl=_is_rtl(text))


def _merge_line_rects(rects: list) -> list[list[float]]:
    """Join the touching per-letter boxes of one match (Arabic gives one per letter) into one box."""
    merged: list[pymupdf.Rect] = []
    for rect in rects:
        for position, line in enumerate(merged):
            overlap = min(line.y1, rect.y1) - max(line.y0, rect.y0)
            gap = max(rect.x0 - line.x1, line.x0 - rect.x1)
            if overlap > 0.5 * min(line.height, rect.height) and gap <= 0.1 * line.height:
                merged[position] = line | rect
                break
        else:
            merged.append(pymupdf.Rect(rect))
    return [[round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)] for r in merged]


def _search_page(page, query: str, target: str | None) -> list:
    """target is the normalised Arabic query. The quick text check skips the slower search on most pages."""
    if target is None:
        return page.search_for(query, quads=False)
    return find_text(page, query) if target in normal_text(page.get_text()) else []


@tool("search")
def search(job: Job, args: dict) -> dict:
    query = str(require(args, "query")).strip()
    target = normal_text(query) if ARABIC_LETTER.search(query) else None
    _, doc = _open_for_viewer(args)
    hits = []
    with doc:
        for index in range(len(doc)):
            if index % 25 == 0:
                job.check_cancelled()
            found = _search_page(doc[index], query, target)
            if found:
                hits.append({"page": index, "rects": _merge_line_rects(found)})
    return result([], hits=hits, total=sum(len(h["rects"]) for h in hits))
