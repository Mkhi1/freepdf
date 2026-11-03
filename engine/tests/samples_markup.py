"""Generated sample files and measuring helpers for the mark-up, redact, compare and language tests."""
import threading
import unicodedata
import warnings
from pathlib import Path

import numpy as np

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pymupdf

from freepdf_engine.core import Job
from freepdf_engine.registry import TOOLS

ARABIC = "مرحبا بالعالم"
PAGE_W, PAGE_H = 595, 842


def run(tool_name: str, args: dict) -> dict:
    """Call a registered tool directly and return its result dict."""
    import importlib
    for module in ("markup", "sign", "redact", "compare", "language"):
        try:
            importlib.import_module(f"freepdf_engine.tools.{module}")
        except ModuleNotFoundError as err:
            if err.name != f"freepdf_engine.tools.{module}":
                raise
    job = Job("t", lambda message: None, threading.Event())
    return TOOLS[tool_name](job, args)


def make_text_pdf(path: Path, pages: int = 3, lines: int = 6) -> Path:
    doc = pymupdf.open()
    for number in range(1, pages + 1):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page.insert_text((72, 90), f"Chapter {number} heading", fontsize=20)
        for row in range(lines):
            page.insert_text((72, 130 + row * 22),
                             f"Line {row + 1} of page {number}: the quick brown fox jumps over the lazy dog.",
                             fontsize=11)
    doc.save(str(path))
    doc.close()
    return path


def make_arabic_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    css = "@font-face{font-family:ar;src:url(arial.ttf);}body{font-family:ar;font-size:16pt;direction:rtl;}"
    archive = pymupdf.Archive(r"C:\Windows\Fonts")
    page.insert_htmlbox(pymupdf.Rect(72, 80, 523, 130), "مرحبا بالعالم هذا اختبار", css=css, archive=archive)
    doc.save(str(path))
    doc.close()
    return path


def render(page_or_path, page_number: int = 0, dpi: int = 72, clip=None) -> np.ndarray:
    """Greyscale pixels of a page as a 2D uint8 array."""
    if isinstance(page_or_path, (str, Path)):
        with pymupdf.open(str(page_or_path)) as doc:
            return render(doc[page_number], dpi=dpi, clip=clip)
    pix = page_or_path.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, clip=clip)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def render_rgb(path: Path, page_number: int = 0, dpi: int = 72) -> np.ndarray:
    with pymupdf.open(str(path)) as doc:
        pix = doc[page_number].get_pixmap(dpi=dpi, alpha=False)
        return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)


def ink_box(pixels: np.ndarray, threshold: int = 200) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(pixels < threshold)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def principal_angle(pixels: np.ndarray, threshold: int = 230) -> float:
    """Counter-clockwise angle of the main axis of the ink, 0 to 180 degrees."""
    ys, xs = np.nonzero(pixels < threshold)
    coords = np.stack([xs - xs.mean(), -(ys - ys.mean())])
    values, vectors = np.linalg.eigh(np.cov(coords))
    major = vectors[:, np.argmax(values)]
    return float(np.degrees(np.arctan2(major[1], major[0])) % 180)


def normal(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def has_joined_forms(raw: str) -> bool:
    """True when extracted Arabic contains initial or medial glyph forms, so letters really joined."""
    return any(unicodedata.decomposition(ch).startswith(("<initial>", "<medial>")) for ch in raw)


def all_text(path: Path) -> str:
    with pymupdf.open(str(path)) as doc:
        return "\n".join(page.get_text() for page in doc)


def raw_streams(path: Path) -> bytes:
    """Every decoded stream in the file, to prove removed content is not hiding anywhere."""
    chunks = []
    with pymupdf.open(str(path)) as doc:
        for xref in range(1, doc.xref_length()):
            try:
                if doc.xref_is_stream(xref):
                    chunks.append(doc.xref_stream(xref) or b"")
            except Exception:
                continue
    return b"\n".join(chunks)


def stream_mentions(path: Path, text: str) -> bool:
    """True if the text appears in any stream or in the file bytes, plain or as a hex string."""
    needle = text.encode("latin-1")
    variants = {needle, needle.hex().encode(), needle.hex().upper().encode()}
    haystacks = [raw_streams(path), Path(path).read_bytes()]
    return any(v in h for v in variants for h in haystacks)
