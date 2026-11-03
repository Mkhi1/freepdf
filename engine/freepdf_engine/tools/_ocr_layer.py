"""Invisible OCR text layer: recognise a page and write the words back as hidden text."""
import io
import logging
import os
from pathlib import Path

from ..core import ToolError, resource_dir
from ._pdf_common import pymupdf

logging.getLogger("fontTools").setLevel(logging.ERROR)

FONT_NAME = "ocrf"
OCR_DPI = 300
MAX_OCR_PIXELS = 60_000_000
# Latin and Arabic text both need glyph coverage; Windows always ships these.
FONT_CANDIDATES = ("arial.ttf", "tahoma.ttf", "segoeui.ttf")
FONT_FOLDERS = (lambda: resource_dir("fonts"), lambda: Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts")


def tessdata_path(languages: list[str]) -> str:
    folder = resource_dir("tessdata")
    for code in languages:
        if not (folder / f"{code}.traineddata").is_file():
            raise ToolError(
                "missing_resource",
                f"The OCR language data for '{code}' is missing. Reinstall Free PDF or add {code}.traineddata to {folder}.",
            )
    return str(folder)


def find_font_file() -> Path:
    for folder in FONT_FOLDERS:
        for name in FONT_CANDIDATES:
            candidate = folder() / name
            if candidate.is_file():
                return candidate
    raise ToolError("missing_resource", "No font with Arabic and Latin letters was found for the OCR text layer.")


def ocr_dpi(page: pymupdf.Page) -> int:
    """Very long pages, such as full-page screenshots, are read at a lower resolution so the image fits."""
    square_inches = page.rect.width * page.rect.height / (72 * 72)
    return min(OCR_DPI, int((MAX_OCR_PIXELS / square_inches) ** 0.5))


def recognise(page: pymupdf.Page, languages: list[str], tessdata: str) -> list[tuple]:
    """Words as (x0, y0, x1, y1, text, block, line, word), in logical reading order per line."""
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    textpage = page.get_textpage_ocr(dpi=ocr_dpi(page), language="+".join(languages), full=True, tessdata=tessdata)
    return [w for w in textpage.extractWORDS() if w[4].strip() and w[2] - w[0] > 0.5 and w[3] - w[1] > 0.5]


def build_font_bytes(words_by_page: list[list[tuple]]) -> bytes:
    """A font cut down to the letters that were recognised, with plain Unicode mapping."""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    used = {ord(c) for words in words_by_page for w in words for c in w[4]} | {0x20}
    font = TTFont(find_font_file())
    options = subset.Options()
    options.layout_features = []
    options.drop_tables += ["meta"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=sorted(used))
    subsetter.subset(font)
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def _is_rtl_char(char: str) -> bool:
    return "\u0590" <= char <= "\u08ff" or "\ufb1d" <= char <= "\ufdff" or "\ufe70" <= char <= "\ufeff"


def visual_order(word: str) -> str:
    """Reorder a word left to right as drawn. MuPDF reads right-to-left runs back to logical order."""
    runs: list[tuple[bool, list[str]]] = []
    for char in word:
        rtl = _is_rtl_char(char)
        if runs and runs[-1][0] == rtl:
            runs[-1][1].append(char)
        else:
            runs.append((rtl, [char]))
    if not any(rtl for rtl, _ in runs):
        return word
    return "".join("".join(reversed(chars)) if rtl else "".join(chars) for rtl, chars in reversed(runs))


def write_words(page: pymupdf.Page, words: list[tuple], font_bytes: bytes, font: pymupdf.Font) -> None:
    """Draw each word invisibly (text render mode 3) at its recognised position and width."""
    if not words:
        return
    page.insert_font(fontname=FONT_NAME, fontbuffer=font_bytes)
    lines: dict[tuple, list[tuple]] = {}
    for word in words:
        lines.setdefault((word[5], word[6]), []).append(word)
    for line in lines.values():
        for x0, y0, x1, y1, text, *_ in sorted(line, key=lambda w: w[0]):
            _write_word(page, font, text, pymupdf.Rect(x0, y0, x1, y1))


def _write_word(page: pymupdf.Page, font: pymupdf.Font, text: str, box: pymupdf.Rect) -> None:
    shown = visual_order(text)
    size = box.height * 0.8
    natural = font.text_length(shown, fontsize=size)
    if natural <= 0:
        return
    origin = pymupdf.Point(box.x0, box.y1 - box.height * 0.2)
    page.insert_text(
        origin, shown, fontname=FONT_NAME, fontsize=size, render_mode=3,
        morph=(origin, pymupdf.Matrix(box.width / natural, 1)),
    )
