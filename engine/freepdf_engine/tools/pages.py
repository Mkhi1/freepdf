"""Page tools: merge, split, organize, rotate, crop."""
import tempfile
import zipfile
from pathlib import Path

from ..core import Job, ToolError, output_path, parse_ranges, require, require_file, result
from ..registry import tool
from ._pdf_common import check_pages, open_pdf, pymupdf, remap_toc, save_pdf, set_toc_safely


def _extract_pages(doc, pages: list[int]):
    """Copy pages (in the given order) into a new document, keeping links and bookmarks."""
    out = pymupdf.open()
    index = 0
    while index < len(pages):
        end = index
        while end + 1 < len(pages) and pages[end + 1] == pages[end] + 1:
            end += 1
        out.insert_pdf(doc, from_page=pages[index], to_page=pages[end])
        index = end + 1
    first_use = {}
    for new_index, old in enumerate(pages):
        first_use.setdefault(old, new_index)
    set_toc_safely(out, remap_toc(doc.get_toc(simple=True), first_use))
    return out


def _write_pdf(out, path: Path) -> None:
    save_pdf(out, path, garbage=3)
    out.close()


@tool("merge")
def merge(job: Job, args: dict) -> dict:
    files = require(args, "files")
    if not isinstance(files, list) or len(files) < 2:
        raise ToolError("bad_args", "Pick at least two PDF files to merge.")
    merged = pymupdf.open()
    toc: list = []
    first_path = None
    for number, item in enumerate(files):
        job.progress(number / len(files), f"Adding file {number + 1} of {len(files)}")
        spec = item if isinstance(item, dict) else {"path": item}
        path = require_file(require(spec, "path"))
        first_path = first_path or path
        with open_pdf(path, spec.get("password") or args.get("password")) as doc:
            offset = len(merged)
            merged.insert_pdf(doc, links=True, annots=True)
            source_toc = doc.get_toc(simple=True)
            page_map = {i: i for i in range(len(doc))}
            toc = [*toc, *remap_toc(source_toc, page_map, offset)]
    set_toc_safely(merged, _repair_levels(toc))
    out_path = output_path(first_path, "merged", out_dir=args.get("out_dir"))
    job.progress(0.95, "Saving")
    _write_pdf(merged, out_path)
    return result([out_path], pages=len(files))


def _repair_levels(toc: list) -> list:
    fixed, previous = [], 0
    for level, title, page in toc:
        level = min(max(level, 1), previous + 1)
        fixed.append([level, title, page])
        previous = level
    return fixed


# --- split ---------------------------------------------------------------

def _range_groups(spec: str, count: int) -> list[tuple[str, list[int]]]:
    groups = []
    for part in [p for p in spec.replace(" ", "").split(",") if p]:
        pages = parse_ranges(part, count)
        groups.append((f"pages {part}" if len(pages) > 1 else f"page {part}", pages))
    if not groups:
        raise ToolError("bad_args", "Enter at least one page range, for example 1-3,7.")
    return groups


def _every_groups(step: int, count: int) -> list[tuple[str, list[int]]]:
    if step < 1:
        raise ToolError("bad_args", "Pages per file must be 1 or more.")
    groups = []
    for start in range(0, count, step):
        pages = list(range(start, min(start + step, count)))
        label = f"page {start + 1}" if len(pages) == 1 else f"pages {start + 1}-{pages[-1] + 1}"
        groups.append((label, pages))
    return groups


def _size_of(doc, pages: list[int]) -> int:
    out = _extract_pages(doc, pages)
    try:
        return len(out.tobytes(garbage=3, deflate=True))
    finally:
        out.close()


def _fit_count(doc, start: int, limit: int, max_bytes: int) -> int:
    """Largest page count from start whose saved file stays under max_bytes (at least 1)."""
    room = limit - start
    low, high = 1, 1
    while high < room and _size_of(doc, list(range(start, start + high))) <= max_bytes:
        low, high = high, min(high * 2, room)
    if high == low:
        return low
    if _size_of(doc, list(range(start, start + high))) <= max_bytes:
        return high
    while high - low > 1:
        mid = (low + high) // 2
        if _size_of(doc, list(range(start, start + mid))) <= max_bytes:
            low = mid
        else:
            high = mid
    return low


def _size_groups(job: Job, doc, max_mb: float) -> tuple[list[tuple[str, list[int]]], int]:
    max_bytes = int(max_mb * 1024 * 1024)
    groups, start, too_big = [], 0, 0
    while start < len(doc):
        job.progress(0.5 * start / len(doc), f"Measuring from page {start + 1}")
        count = _fit_count(doc, start, len(doc), max_bytes)
        pages = list(range(start, start + count))
        if count == 1 and _size_of(doc, pages) > max_bytes:
            too_big += 1
        label = f"page {start + 1}" if count == 1 else f"pages {start + 1}-{start + count}"
        groups.append((label, pages))
        start += count
    return groups, too_big


def _split_groups(job: Job, doc, args: dict) -> tuple[list[tuple[str, list[int]]], dict]:
    mode = require(args, "mode")
    count = len(doc)
    if mode == "ranges":
        groups = _range_groups(str(require(args, "ranges")), count)
    elif mode == "extract":
        pages = parse_ranges(str(require(args, "ranges")), count)
        groups = [(f"page {p + 1}", [p]) for p in pages]
    elif mode == "every":
        groups = _every_groups(int(require(args, "every")), count)
    elif mode == "extract_all":
        groups = _every_groups(1, count)
    elif mode == "size":
        try:
            max_mb = float(require(args, "max_mb"))
        except (TypeError, ValueError) as err:
            raise ToolError("bad_args", "Maximum size must be a number of megabytes.") from err
        if max_mb <= 0:
            raise ToolError("bad_args", "Maximum size must be more than 0 MB.")
        groups, too_big = _size_groups(job, doc, max_mb)
        return groups, {"pages_over_limit": too_big}
    else:
        raise ToolError("bad_args", f"Unknown split mode: {mode}.")
    if args.get("merge_output"):
        merged = [p for _, pages in groups for p in pages]
        groups = [("extracted", merged)]
    return groups, {}


@tool("split")
def split(job: Job, args: dict) -> dict:
    src = require_file(require(args, "file"))
    out_dir = args.get("out_dir")
    with open_pdf(src, args.get("password")) as doc:
        groups, extra = _split_groups(job, doc, args)
        want_zip = bool(args.get("zip")) and len(groups) > 1
        with tempfile.TemporaryDirectory(prefix="freepdf-split-") as scratch:
            target = scratch if want_zip else out_dir
            paths = _write_groups(job, doc, src, groups, target)
            if want_zip:
                paths = [_zip_parts(paths, src, out_dir)]
    return result(paths, parts=len(groups), zipped=want_zip, **extra)


def _write_groups(job: Job, doc, src: Path, groups, target) -> list[Path]:
    paths = []
    for number, (label, pages) in enumerate(groups):
        job.progress(0.5 + 0.5 * number / len(groups), f"Writing file {number + 1} of {len(groups)}")
        path = output_path(src, label, out_dir=target)
        _write_pdf(_extract_pages(doc, pages), path)
        paths.append(path)
    return paths


def _zip_parts(paths: list[Path], src: Path, out_dir) -> Path:
    zip_path = output_path(src, "split", ".zip", out_dir)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as archive:
        for path in paths:
            archive.write(path, path.name)
    return zip_path


# --- organize, rotate, crop ---------------------------------------------------

def _blank_size(out) -> tuple[float, float]:
    if len(out):
        rect = out[-1].rect
        return rect.width, rect.height
    return 595.0, 842.0


def _check_angle(value) -> int:
    try:
        angle = int(value)
    except (TypeError, ValueError) as err:
        raise ToolError("bad_args", "Rotation must be 90, 180 or 270 degrees.") from err
    if angle % 90 != 0:
        raise ToolError("bad_args", "Rotation must be 90, 180 or 270 degrees.")
    return angle % 360


@tool("organize")
def organize(job: Job, args: dict) -> dict:
    main = require_file(require(args, "file"))
    items = require(args, "pages")
    if not isinstance(items, list) or not items:
        raise ToolError("bad_args", "Keep at least one page.")
    sources: dict[str, pymupdf.Document] = {}
    out = pymupdf.open()
    try:
        for number, item in enumerate(items):
            job.progress(number / len(items), f"Page {number + 1} of {len(items)}")
            _add_item(out, item, main, sources, args.get("password"))
        out_path = output_path(main, "organized", out_dir=args.get("out_dir"))
        save_pdf(out, out_path, garbage=4)
    finally:
        out.close()
        for doc in sources.values():
            doc.close()
    return result([out_path], pages=len(items))


def _add_item(out, item: dict, main: Path, sources: dict, password) -> None:
    rotate = _check_angle(item.get("rotate", 0))
    if item.get("blank"):
        width, height = _blank_size(out)
        page = out.new_page(width=width, height=height)
    else:
        path = require_file(item.get("source") or str(main))
        key = str(path)
        if key not in sources:
            sources[key] = open_pdf(path, password)
        src = sources[key]
        index = check_pages([item.get("page", 0)], len(src))[0]
        out.insert_pdf(src, from_page=index, to_page=index)
        page = out[-1]
    if rotate:
        page.set_rotation((page.rotation + rotate) % 360)


@tool("rotate")
def rotate(job: Job, args: dict) -> dict:
    src = require_file(require(args, "file"))
    angle = _check_angle(require(args, "angle"))
    if angle == 0:
        raise ToolError("bad_args", "Rotation must be 90, 180 or 270 degrees.")
    with open_pdf(src, args.get("password")) as doc:
        pages = check_pages(args.get("pages"), len(doc))
        for number, index in enumerate(pages):
            job.progress(number / len(pages))
            page = doc[index]
            page.set_rotation((page.rotation + angle) % 360)
        out_path = output_path(src, "rotated", out_dir=args.get("out_dir"))
        save_pdf(doc, out_path, garbage=1)
    return result([out_path], pages=len(pages))


def _check_box(box) -> pymupdf.Rect:
    try:
        x0, y0, x1, y1 = (float(v) for v in box)
    except (TypeError, ValueError) as err:
        raise ToolError("bad_args", "The crop area must be four numbers: left, top, right, bottom.") from err
    rect = pymupdf.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    if rect.is_empty:
        raise ToolError("bad_args", "The crop area is empty. Drag a larger area.")
    return rect


@tool("crop")
def crop(job: Job, args: dict) -> dict:
    src = require_file(require(args, "file"))
    box = _check_box(require(args, "box"))
    with open_pdf(src, args.get("password")) as doc:
        pages = check_pages(args.get("pages"), len(doc))
        for number, index in enumerate(pages):
            job.progress(number / len(pages))
            page = doc[index]
            visible = box & page.rect
            if visible.is_empty:
                raise ToolError("bad_args", f"The crop area is outside page {index + 1}.")
            page.set_cropbox(visible * page.derotation_matrix)
        out_path = output_path(src, "cropped", out_dir=args.get("out_dir"))
        save_pdf(doc, out_path, garbage=1)
    return result([out_path], pages=len(pages))
