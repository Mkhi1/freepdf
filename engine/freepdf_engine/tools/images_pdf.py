"""Images to PDF. JPEG data is embedded byte for byte, never recompressed."""
import io
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from ..convert_util import file_list
from ..core import Job, ToolError, output_path, result
from ..registry import tool

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
PAGE_SIZES = {"a4": (595.276, 841.89), "letter": (612.0, 792.0)}
MARGINS = {"none": 0.0, "small": 20.0, "big": 50.0}
MAX_PAGE_POINTS = 14400.0
ROTATION_ONLY = {3: 180, 6: 270, 8: 90}  # EXIF orientation to clockwise rotation needed


@dataclass(frozen=True)
class Prepared:
    """Image bytes ready for PDF embedding, its visible size in pixels and in points, and a rotation."""
    data: bytes
    rotate: int
    width_pt: float
    height_pt: float


def _natural_points(width: int, height: int, dpi: tuple[float, float] | None) -> tuple[float, float]:
    x_dpi, y_dpi = (dpi if dpi and dpi[0] >= 36 and dpi[1] >= 36 else (96.0, 96.0))
    return width * 72.0 / x_dpi, height * 72.0 / y_dpi


def _png_bytes(img: Image.Image) -> bytes:
    if img.mode not in ("RGB", "RGBA", "L", "LA", "1"):
        img = img.convert("RGBA" if "transparency" in img.info or img.mode == "P" else "RGB")
    if img.mode in ("LA", "1"):
        img = img.convert("RGBA" if img.mode == "LA" else "L")
    buffer = io.BytesIO()
    img.save(buffer, "PNG")
    return buffer.getvalue()


def _prepare_jpeg(path: Path, img: Image.Image, orientation: int) -> Prepared | None:
    if img.mode not in ("RGB", "L") or orientation not in (0, 1, 3, 6, 8):
        return None
    rotate = ROTATION_ONLY.get(orientation, 0)
    width, height = img.size
    if rotate in (90, 270):
        width, height = height, width
    w_pt, h_pt = _natural_points(width, height, _dpi_of(img))
    return Prepared(path.read_bytes(), rotate, w_pt, h_pt)


def _dpi_of(img: Image.Image) -> tuple[float, float] | None:
    dpi = img.info.get("dpi")
    if isinstance(dpi, tuple) and len(dpi) == 2 and all(isinstance(v, (int, float)) for v in dpi):
        return float(dpi[0]), float(dpi[1])
    return None


def prepare_image(path: Path) -> Prepared:
    try:
        img = Image.open(path)
        if img.format != "JPEG":
            img.load()
    except Exception:
        raise ToolError("bad_args", f"{path.name} could not be read as an image.")
    orientation = int(img.getexif().get(274, 1) or 1)
    dpi = _dpi_of(img)
    if img.format == "JPEG":
        direct = _prepare_jpeg(path, img, orientation)
        if direct:
            return direct
        img.load()
    flat = ImageOps.exif_transpose(img) if orientation not in (0, 1) else img
    if img.format == "JPEG":
        buffer = io.BytesIO()
        flat.convert("RGB").save(buffer, "JPEG", quality=95, subsampling=0, dpi=dpi or (96, 96))
        data = buffer.getvalue()
    else:
        if getattr(flat, "n_frames", 1) > 1:
            flat.seek(0)
        data = _png_bytes(flat)
    w_pt, h_pt = _natural_points(flat.width, flat.height, dpi)
    return Prepared(data, 0, w_pt, h_pt)


def _page_box(prep: Prepared, page_size: str, orientation: str, margin_pt: float) -> tuple[float, float, pymupdf.Rect]:
    if page_size == "fit":
        scale = min(1.0, (MAX_PAGE_POINTS - 2 * margin_pt) / max(prep.width_pt, prep.height_pt))
        w, h = prep.width_pt * scale + 2 * margin_pt, prep.height_pt * scale + 2 * margin_pt
        return w, h, pymupdf.Rect(margin_pt, margin_pt, w - margin_pt, h - margin_pt)
    base_w, base_h = PAGE_SIZES[page_size]
    if orientation == "auto":
        orientation = "landscape" if prep.width_pt > prep.height_pt else "portrait"
    w, h = (base_h, base_w) if orientation == "landscape" else (base_w, base_h)
    box_w, box_h = w - 2 * margin_pt, h - 2 * margin_pt
    scale = min(box_w / prep.width_pt, box_h / prep.height_pt, 1.0)
    draw_w, draw_h = prep.width_pt * scale, prep.height_pt * scale
    left, top = (w - draw_w) / 2, (h - draw_h) / 2
    return w, h, pymupdf.Rect(left, top, left + draw_w, top + draw_h)


def _add_page(doc: pymupdf.Document, prep: Prepared, page_size: str, orientation: str, margin_pt: float) -> None:
    w, h, rect = _page_box(prep, page_size, orientation, margin_pt)
    page = doc.new_page(width=w, height=h)
    page.insert_image(rect, stream=prep.data, rotate=prep.rotate, keep_proportion=False)


def _options(args: dict) -> tuple[str, str, float]:
    page_size = str(args.get("page_size", "fit")).lower()
    orientation = str(args.get("orientation", "portrait")).lower()
    margin = str(args.get("margin", "none")).lower()
    if page_size not in (*PAGE_SIZES, "fit"):
        raise ToolError("bad_args", "Page size must be fit, a4 or letter.")
    if orientation not in ("portrait", "landscape", "auto"):
        raise ToolError("bad_args", "Orientation must be portrait or landscape.")
    if margin not in MARGINS:
        raise ToolError("bad_args", "Margin must be none, small or big.")
    return page_size, orientation, MARGINS[margin]


def _save(doc: pymupdf.Document, target: Path) -> Path:
    doc.save(str(target), garbage=3, deflate=True)
    doc.close()
    return target


@tool("images_to_pdf")
def images_to_pdf(job: Job, args: dict) -> dict:
    files = file_list(args)
    for path in files:
        if path.suffix.lower() not in IMAGE_EXTS:
            raise ToolError("bad_args", f"{path.name} is not a supported image. Use JPG, PNG, WebP, BMP, TIFF or GIF.")
    page_size, orientation, margin_pt = _options(args)
    merge = bool(args.get("merge_output", True)) or len(files) == 1
    out_dir = args.get("out_dir")
    outputs: list[Path] = []
    doc = pymupdf.open()
    for index, path in enumerate(files):
        job.progress(index / len(files), f"Adding {path.name}")
        _add_page(doc, prepare_image(path), page_size, orientation, margin_pt)
        if not merge:
            outputs = [*outputs, _save(doc, output_path(path, "", ".pdf", out_dir))]
            doc = pymupdf.open()
    if merge:
        label = "" if len(files) == 1 else "images"
        outputs = [_save(doc, output_path(files[0], label, ".pdf", out_dir))]
    else:
        doc.close()
    return result(outputs, images=len(files))
