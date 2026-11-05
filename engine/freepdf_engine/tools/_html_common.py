"""Shared pieces for turning Office files into HTML that Edge prints, used when Office is not installed."""
import base64
import html
import re

ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
BASE_CSS = (
    "*{box-sizing:border-box}html,body{margin:0;padding:0}"
    "body{font-family:Calibri,'Segoe UI',Arial,sans-serif;color:#000;-webkit-print-color-adjust:exact;print-color-adjust:exact}"
    "p{margin:0}table{border-collapse:collapse}img{max-width:100%}"
)
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
               "bmp": "image/bmp", "tif": "image/tiff", "tiff": "image/tiff", "emf": "image/emf", "wmf": "image/wmf",
               "svg": "image/svg+xml", "webp": "image/webp"}


def esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def text_dir(text: str) -> str:
    """'rtl' when the first strong letter is Arabic, so mixed paragraphs read in the right order."""
    for char in text or "":
        if ARABIC.match(char):
            return "rtl"
        if char.isalpha():
            return "ltr"
    return "auto"


def data_uri(blob: bytes, ext_or_type: str) -> str:
    kind = ext_or_type if "/" in ext_or_type else IMAGE_TYPES.get(ext_or_type.lower().lstrip("."), "image/png")
    return f"data:{kind};base64,{base64.b64encode(blob).decode('ascii')}"


def hex_color(color) -> str | None:
    """'#RRGGBB' from a python-docx/pptx RGBColor or a hex string, None when unset."""
    if color is None:
        return None
    text = str(color).strip().lstrip("#")
    if len(text) == 8:  # ARGB from openpyxl
        text = text[2:]
    return f"#{text}" if re.fullmatch(r"[0-9A-Fa-f]{6}", text) else None


def style(**props) -> str:
    """Inline CSS from keyword props; underscores become dashes and empty values are dropped."""
    parts = [f"{key.replace('_', '-')}:{value}" for key, value in props.items() if value not in (None, "")]
    return f' style="{";".join(parts)}"' if parts else ""


def page_css(width_in: float, height_in: float, margins_in: tuple[float, float, float, float] = (0, 0, 0, 0)) -> str:
    top, right, bottom, left = margins_in
    return f"@page{{size:{width_in:.3f}in {height_in:.3f}in;margin:{top:.3f}in {right:.3f}in {bottom:.3f}in {left:.3f}in}}"


def document(body: str, css: str, lang_dir: str = "ltr") -> str:
    return (f"<!doctype html><html dir=\"{lang_dir}\"><head><meta charset=\"utf-8\">"
            f"<style>{BASE_CSS}{css}</style></head><body>{body}</body></html>")
