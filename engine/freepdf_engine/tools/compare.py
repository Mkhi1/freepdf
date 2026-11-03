"""Compare two PDFs by words or by pixels, with a PDF report that marks every difference."""
import difflib
import unicodedata
import warnings

import numpy as np

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pymupdf

from ..core import Job, ToolError, output_path, require, result
from ..registry import tool
from ._mk_io import open_doc

VISUAL_DPI = 100
PIXEL_THRESHOLD = 40
REGION_GROW = 6
MIN_REGION_PIXELS = 12
ADDED_COLOR = (0.1, 0.65, 0.25)
REMOVED_COLOR = (0.85, 0.1, 0.1)


def _page_words(page) -> list[tuple]:
    return [(unicodedata.normalize("NFKC", w[4]), pymupdf.Rect(w[:4]), (w[5], w[6]))
            for w in page.get_text("words")]


def _merge_by_line(words: list[tuple]) -> list[dict]:
    """Join neighbouring words on one line into a single rectangle with their text."""
    merged: list[dict] = []
    last_line = None
    for text, rect, line in words:
        if merged and line == last_line:
            merged[-1]["text"] += " " + text
            merged[-1]["_rect"] = pymupdf.Rect(merged[-1]["_rect"]).include_rect(rect)
        else:
            merged.append({"text": text, "_rect": pymupdf.Rect(rect)})
        last_line = line
    return [{"text": m["text"], "rect": [round(v, 2) for v in m["_rect"]]} for m in merged]


def diff_words(words_a: list[tuple], words_b: list[tuple]) -> tuple[list[dict], list[dict]]:
    matcher = difflib.SequenceMatcher(None, [w[0] for w in words_a], [w[0] for w in words_b], autojunk=False)
    removed, added = [], []
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            removed.extend(words_a[a0:a1])
        if tag in ("insert", "replace"):
            added.extend(words_b[b0:b1])
    return _merge_by_line(removed), _merge_by_line(added)


def _signature(page) -> str:
    return " ".join(w[0] for w in _page_words(page))


def align_pages(doc_a, doc_b) -> list[tuple[int | None, int | None]]:
    """Pair pages by content so an inserted or deleted page does not shift everything after it."""
    sig_a = [_signature(p) for p in doc_a]
    sig_b = [_signature(p) for p in doc_b]
    pairs: list[tuple[int | None, int | None]] = []
    matcher = difflib.SequenceMatcher(None, sig_a, sig_b, autojunk=False)
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        count = max(a1 - a0, b1 - b0)
        for step in range(count):
            a = a0 + step if a0 + step < a1 else None
            b = b0 + step if b0 + step < b1 else None
            pairs.append((a, b))
    return pairs


def compare_text(job: Job, doc_a, doc_b) -> list[dict]:
    pairs = align_pages(doc_a, doc_b)
    pages = []
    for number, (a, b) in enumerate(pairs):
        job.progress(number / max(len(pairs), 1) * 0.8, f"Comparing page {number + 1} of {len(pairs)}")
        words_a = _page_words(doc_a[a]) if a is not None else []
        words_b = _page_words(doc_b[b]) if b is not None else []
        removed, added = diff_words(words_a, words_b)
        pages.append({"page": number, "page_a": a, "page_b": b, "added": added, "removed": removed,
                      "changed": bool(added or removed)})
    return pages


def _render_gray(page, scale: float, canvas: tuple[int, int]) -> np.ndarray:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csGRAY, alpha=False)
    flat = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    sheet = np.full((canvas[1], canvas[0]), 255, dtype=np.uint8)
    sheet[:min(pix.height, canvas[1]), :min(pix.width, canvas[0])] = flat[:canvas[1], :canvas[0]]
    return sheet


def _regions(mask: np.ndarray, scale: float) -> list[list[float]]:
    import cv2

    grown = cv2.dilate(mask.astype(np.uint8), np.ones((REGION_GROW * 2 + 1,) * 2, np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(grown)
    boxes = []
    for x, y, w, h, area in stats[1:]:
        if area >= MIN_REGION_PIXELS:
            boxes.append([round(x / scale, 1), round(y / scale, 1), round((x + w) / scale, 1), round((y + h) / scale, 1)])
    return boxes


def _diff_image(gray_a: np.ndarray, gray_b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """RGB picture: unchanged content faint grey, removed content red, added content green."""
    a, b = gray_a.astype(np.int16), gray_b.astype(np.int16)
    removed = (b - a) > PIXEL_THRESHOLD       # darker in A only
    added = (a - b) > PIXEL_THRESHOLD         # darker in B only
    base = (255 - (255 - np.minimum(a, b)) * 0.3).astype(np.uint8)
    rgb = np.stack([base, base, base], axis=-1)
    rgb[removed] = (220, 30, 30)
    rgb[added] = (20, 160, 60)
    return rgb, removed | added


def compare_visual(job: Job, doc_a, doc_b, args: dict, source) -> tuple[list[dict], list]:
    dpi = float(args.get("dpi", VISUAL_DPI))
    scale = dpi / 72
    pairs = align_pages(doc_a, doc_b)
    pages, images = [], []
    for number, (a, b) in enumerate(pairs):
        job.progress(number / max(len(pairs), 1) * 0.8, f"Comparing page {number + 1} of {len(pairs)}")
        size_a = doc_a[a].rect if a is not None else pymupdf.Rect(0, 0, 1, 1)
        size_b = doc_b[b].rect if b is not None else pymupdf.Rect(0, 0, 1, 1)
        canvas = (int(max(size_a.width, size_b.width) * scale), int(max(size_a.height, size_b.height) * scale))
        blank = np.full((canvas[1], canvas[0]), 255, dtype=np.uint8)
        gray_a = _render_gray(doc_a[a], scale, canvas) if a is not None else blank
        gray_b = _render_gray(doc_b[b], scale, canvas) if b is not None else blank
        rgb, mask = _diff_image(gray_a, gray_b)
        path = output_path(source, f"compare page {number + 1}", ".png", args.get("out_dir"))
        _write_png(path, rgb)
        images.append(path)
        pages.append({"page": number, "page_a": a, "page_b": b, "image": str(path),
                      "difference_percent": round(float(mask.mean()) * 100, 3), "regions": _regions(mask, scale),
                      "changed": bool(mask.sum() >= MIN_REGION_PIXELS), "size_changed":
                      bool(a is not None and b is not None and (abs(size_a.width - size_b.width) > 1
                                                                or abs(size_a.height - size_b.height) > 1))})
    return pages, images


def _write_png(path, rgb: np.ndarray) -> None:
    pix = pymupdf.Pixmap(pymupdf.csRGB, rgb.shape[1], rgb.shape[0], rgb.tobytes(), False)
    pix.save(str(path))


def _mark(page, rects, color, fill_opacity=0.25) -> None:
    for rect in rects:
        shape = page.new_shape()
        shape.draw_rect(pymupdf.Rect(rect))
        shape.finish(color=color, fill=color, width=0.8, fill_opacity=fill_opacity, stroke_opacity=0.9)
        shape.commit()


def build_report(doc_a, doc_b, pages: list[dict], mode: str, names: tuple[str, str]) -> pymupdf.Document:
    report = pymupdf.open()
    _summary_page(report, pages, mode, names)
    for entry in pages:
        a, b = entry["page_a"], entry["page_b"]
        size_a = doc_a[a].rect if a is not None else None
        size_b = doc_b[b].rect if b is not None else None
        width = max(r.width for r in (size_a, size_b) if r)
        height = max(r.height for r in (size_a, size_b) if r)
        page = report.new_page(width=width * 2 + 24, height=height + 36)
        page.insert_text((12, 20), f"Page {entry['page'] + 1}   left: {names[0]} p.{'-' if a is None else a + 1}"
                         f"   right: {names[1]} p.{'-' if b is None else b + 1}", fontsize=9)
        left = pymupdf.Rect(0, 30, width, 30 + height)
        right = pymupdf.Rect(width + 24, 30, width * 2 + 24, 30 + height)
        if a is not None:
            page.show_pdf_page(pymupdf.Rect(left.x0, left.y0, left.x0 + size_a.width, left.y0 + size_a.height), doc_a, a)
        if b is not None:
            page.show_pdf_page(pymupdf.Rect(right.x0, right.y0, right.x0 + size_b.width, right.y0 + size_b.height), doc_b, b)
        _mark_page(page, entry, mode, left, right)
    return report


def _mark_page(page, entry, mode, left, right) -> None:
    shift_left = pymupdf.Matrix(1, 0, 0, 1, left.x0, left.y0)
    shift_right = pymupdf.Matrix(1, 0, 0, 1, right.x0, right.y0)
    if mode == "text":
        _mark(page, [pymupdf.Rect(i["rect"]) * shift_left for i in entry["removed"]], REMOVED_COLOR)
        _mark(page, [pymupdf.Rect(i["rect"]) * shift_right for i in entry["added"]], ADDED_COLOR)
    else:
        _mark(page, [pymupdf.Rect(r) * shift_left for r in entry["regions"]], REMOVED_COLOR, 0.12)
        _mark(page, [pymupdf.Rect(r) * shift_right for r in entry["regions"]], ADDED_COLOR, 0.12)


def _summary_page(report, pages, mode, names) -> None:
    page = report.new_page(width=595, height=842)
    changed = [p for p in pages if p["changed"]]
    lines = [f"Comparison report ({mode} mode)", "", f"Left (old):  {names[0]}", f"Right (new): {names[1]}", "",
             f"Pages compared: {len(pages)}", f"Pages with differences: {len(changed)}"]
    if mode == "text":
        lines += [f"Words or lines added: {sum(len(p['added']) for p in pages)}",
                  f"Words or lines removed: {sum(len(p['removed']) for p in pages)}"]
    lines += ["", "Red marks content only in the left file. Green marks content only in the right file."]
    for index, text in enumerate(lines):
        page.insert_text((60, 80 + index * 20), text, fontsize=16 if index == 0 else 11)


def _scanned_warning(doc_a, doc_b) -> bool:
    return not any(p.get_text().strip() for p in list(doc_a) + list(doc_b))


@tool("compare")
def compare(job: Job, args: dict) -> dict:
    mode = args.get("mode", "text")
    if mode not in ("text", "visual"):
        raise ToolError("bad_args", 'Compare mode must be "text" or "visual".')
    doc_a = open_doc(args, "file_a")
    doc_b = open_doc({"file_b": require(args, "file_b"), "password": args.get("password_b")}, "file_b")
    source = args["file_a"]
    images: list = []
    if mode == "text":
        pages = compare_text(job, doc_a, doc_b)
    else:
        pages, images = compare_visual(job, doc_a, doc_b, args, source)
    names = (str(source).replace("\\", "/").split("/")[-1], str(args["file_b"]).replace("\\", "/").split("/")[-1])
    report = build_report(doc_a, doc_b, pages, mode, names)
    report_path = output_path(source, "comparison", ".pdf", args.get("out_dir"))
    report.save(str(report_path), garbage=3, deflate=True)
    note = "No text found. Use visual mode for scanned files." if mode == "text" and _scanned_warning(doc_a, doc_b) else ""
    pages_a, pages_b = doc_a.page_count, doc_b.page_count
    doc_a.close(), doc_b.close(), report.close()
    outputs = [report_path, *images]
    return result(outputs, mode=mode, pages=pages, pages_a=pages_a, pages_b=pages_b,
                  changed_pages=sum(p["changed"] for p in pages), report=str(report_path), note=note)
