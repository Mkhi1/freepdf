"""Text search that also finds Arabic stored as joined presentation forms."""
import re
import unicodedata

from ._pdf_common import pymupdf


def normal_char(ch: str) -> str:
    folded = unicodedata.normalize("NFKC", ch).lower()
    return folded if folded.strip() or ch == " " else " "


def normal_text(text: str) -> str:
    return "".join(normal_char(c) for c in text)


def _line_chars(page) -> list[list[tuple[str, pymupdf.Rect]]]:
    """Every text line as (normalised character, box) pairs; one letter may expand to two."""
    lines = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            chars = []
            for span in line["spans"]:
                for char in span["chars"]:
                    box = pymupdf.Rect(char["bbox"])
                    chars.extend((c, box) for c in normal_char(char["c"]))
            lines.append(chars)
    return lines


def find_text(page, needle: str, case_sensitive: bool = False) -> list[pymupdf.Rect]:
    """Boxes of every match, including Arabic that was stored as joined presentation forms."""
    target = normal_text(needle) if not case_sensitive else needle
    boxes: list[pymupdf.Rect] = []
    for chars in _line_chars(page):
        flat = "".join(c for c, _ in chars)
        for match in re.finditer(re.escape(target), flat):
            covered = [box for _, box in chars[match.start():match.end()]]
            if not covered:
                continue
            merged = pymupdf.Rect(covered[0])
            for box in covered[1:]:
                merged.include_rect(box)
            boxes.append(merged)
    for rect in page.search_for(needle):
        if not any((rect & known).get_area() > rect.get_area() * 0.5 for known in boxes):
            boxes.append(rect)
    return boxes
