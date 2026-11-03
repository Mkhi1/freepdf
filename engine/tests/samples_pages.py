"""Generated sample PDFs for the page, optimize, secure and viewer tests."""
import io
import warnings
from pathlib import Path

import numpy as np

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pymupdf

FONTS = Path(r"C:\Windows\Fonts")
ARABIC_CSS = "@font-face{font-family:ar;src:url(arial.ttf);}"


def text_pdf(path: Path, pages: int = 5, size=(595, 842), toc: bool = True, links: bool = True) -> Path:
    doc = pymupdf.open()
    for number in range(pages):
        page = doc.new_page(width=size[0], height=size[1])
        page.insert_text((72, 100), f"Chapter {number + 1} heading", fontsize=24)
        page.insert_text((72, 140), f"Body text of page {number + 1} with the unique word zebra{number + 1}.", fontsize=12)
        page.draw_rect(pymupdf.Rect(72, 200, 300, 260), color=(0, 0, 1), fill=(0.8, 0.9, 1))
        page.insert_text((72, 315), "go to next page", fontsize=11)
    if links:
        for number in range(pages - 1):
            rect = pymupdf.Rect(72, 300, 220, 320)
            doc[number].insert_link({"kind": pymupdf.LINK_GOTO, "from": rect, "page": number + 1, "to": pymupdf.Point(0, 0)})
    if toc:
        doc.set_toc([[1, f"Chapter {i + 1}", i + 1] for i in range(pages)])
    doc.save(str(path), garbage=3, deflate=True)
    doc.close()
    return path


def photo_array(width: int, height: int, seed: int) -> np.ndarray:
    """A photo-like image: smooth colour fields plus film grain."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    base = np.stack([
        128 + 100 * np.sin(x / 90 + seed), 128 + 100 * np.sin(y / 70 + seed), 128 + 100 * np.sin((x + y) / 120),
    ], axis=-1)
    grain = rng.normal(0, 14, size=base.shape)
    return np.clip(base + grain, 0, 255).astype(np.uint8)


def image_heavy_pdf(path: Path, pages: int = 3) -> Path:
    """Pages with large lossless and JPEG photos at high resolution, plus real text."""
    doc = pymupdf.open()
    for number in range(pages):
        page = doc.new_page()
        page.insert_text((72, 60), f"Photo report page {number + 1} quokka{number + 1}", fontsize=16)
        array = photo_array(1600, 1100, number)
        pix = pymupdf.Pixmap(pymupdf.csRGB, 1600, 1100, array.tobytes(), False)
        if number % 2 == 0:
            page.insert_image(pymupdf.Rect(36, 90, 559, 450), pixmap=pix)
        else:
            page.insert_image(pymupdf.Rect(36, 90, 559, 450), stream=pix.tobytes("jpeg", jpg_quality=95))
        page.insert_image(pymupdf.Rect(36, 470, 559, 800), stream=_png(photo_array(1500, 950, 9 + number)))
    doc.save(str(path), garbage=1, deflate=True)
    doc.close()
    return path


def _png(array: np.ndarray) -> bytes:
    from PIL import Image
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, "PNG")
    return buffer.getvalue()


def scanned_pdf(path: Path, english: str, arabic: str) -> Path:
    """An image-only PDF: the words are pixels, with no text layer."""
    source = pymupdf.open()
    page = source.new_page()
    html = (
        f'<div style="font-family:ar;font-size:30pt">{english}</div>'
        f'<div dir="rtl" style="font-family:ar;font-size:30pt">{arabic}</div>'
        f'<div style="font-family:ar;font-size:30pt">Closing line for the scan</div>'
    )
    page.insert_htmlbox(pymupdf.Rect(40, 40, 550, 400), html, css=ARABIC_CSS, archive=pymupdf.Archive(str(FONTS)))
    pix = page.get_pixmap(dpi=200)
    scan = pymupdf.open()
    target = scan.new_page(width=page.rect.width, height=page.rect.height)
    target.insert_image(target.rect, pixmap=pix)
    scan.save(str(path), deflate=True)
    scan.close()
    source.close()
    return path


def damaged_pdfs(source: Path, folder: Path) -> dict[str, Path]:
    """Copies of source that are cut short or have a broken cross-reference table."""
    data = source.read_bytes()
    truncated = folder / "truncated.pdf"
    truncated.write_bytes(data[: int(len(data) * 0.8)])
    broken = folder / "broken-xref.pdf"
    marker = data.rfind(b"startxref")
    broken.write_bytes(data[:marker] + b"startxref\n999999\n%%EOF\n")
    return {"truncated": truncated, "broken-xref": broken}


def render(path: Path, page: int = 0, dpi: int = 60, password: str | None = None) -> np.ndarray:
    with pymupdf.open(str(path)) as doc:
        if doc.needs_pass:
            doc.authenticate(password or "")
        pix = doc[page].get_pixmap(dpi=dpi, alpha=False)
        return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3).astype(np.float32)


def difference(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute pixel difference on a 0 to 255 scale. Different shapes count as very different."""
    if a.shape != b.shape:
        return 255.0
    return float(np.abs(a - b).mean())


def page_text(path: Path, page: int, password: str | None = None) -> str:
    with pymupdf.open(str(path)) as doc:
        if doc.needs_pass:
            doc.authenticate(password or "")
        return doc[page].get_text()


def call(tool_name: str, args: dict) -> dict:
    """Run a tool in-process the way the engine loop does, returning its result dict."""
    import importlib
    import threading

    from freepdf_engine.core import Job
    from freepdf_engine.registry import TOOLS

    for module in ("pages", "optimize", "secure", "viewer"):
        try:
            importlib.import_module(f"freepdf_engine.tools.{module}")
        except ModuleNotFoundError:
            pass
    job = Job("test", lambda message: None, threading.Event())
    return TOOLS[tool_name](job, args)
