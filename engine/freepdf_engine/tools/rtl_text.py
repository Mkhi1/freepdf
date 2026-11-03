"""Reading-order repair for right-to-left pages.

PDF text for Arabic is stored in visual order, so a plain extraction can return words
left to right and digit runs reversed. Here lines are rebuilt in logical order from word positions.
"""
import re
from collections import defaultdict

import pymupdf

ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
ARABIC_DIGITS = re.compile(r"^[٠-٩۰-۹][٠-٩۰-۹.,٫٬%]*$")


DIGIT_WORD = re.compile(r"[٠-٩۰-۹]{2}")


def needs_fix(text: str) -> bool:
    return has_arabic(text) or bool(DIGIT_WORD.search(text))


def has_arabic(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(1 for c in letters if ARABIC.match(c)) / len(letters) > 0.3


def _logical_words(words: list[tuple]) -> list[str]:
    """Words of one RTL line, given as (x0, text), in logical reading order."""
    ordered = sorted(words, key=lambda w: -w[0])  # right to left
    out: list[str] = []
    run: list[str] = []
    for _, text in ordered:
        if ARABIC_DIGITS.match(text):
            out, run = [*out, *reversed(run), text[::-1]], []
        elif ARABIC.search(text):
            out, run = [*out, *reversed(run), text], []
        else:
            run = [*run, text]  # latin words and western numbers read left to right inside the run
    return [*out, *reversed(run)]


def logical_line(words: list[tuple]) -> str:
    """One line from (x0, text) words: left to right, or logical order when it needs repair."""
    joined = " ".join(text for _, text in sorted(words, key=lambda w: w[0]))
    return " ".join(_logical_words(words)) if needs_fix(joined) else joined


def lines_of(page: pymupdf.Page, clip: pymupdf.Rect | None = None) -> list[tuple[int, float, str]]:
    """Text lines as (block, top, text) in reading order, Arabic lines in logical order."""
    groups: dict[tuple[int, int], list[tuple]] = defaultdict(list)
    for x0, y0, x1, y1, text, block, line, _ in page.get_text("words", clip=clip):
        groups[(block, line)].append((x0, y0, text))
    result = []
    for (block, _), items in sorted(groups.items()):
        result.append((block, min(i[1] for i in items), logical_line([(i[0], i[2]) for i in items])))
    return result


def page_text(page: pymupdf.Page, clip: pymupdf.Rect | None = None) -> str:
    plain = page.get_text("text", clip=clip)
    if not needs_fix(plain):
        return plain
    blocks: dict[int, list[str]] = defaultdict(list)
    for block, _, text in lines_of(page, clip):
        blocks[block].append(text)
    paragraphs = ["\n".join(lines) for lines in blocks.values()]
    return "\n\n".join(paragraphs) + "\n"
