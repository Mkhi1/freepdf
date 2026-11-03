"""Translate (layout kept, offline) and summarize (extractive, offline)."""
import re
import statistics
import warnings
from pathlib import Path

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pymupdf

from ..core import Job, ToolError, output_path, parse_ranges, require, result
from ..registry import tool
from . import _lang_engine as engine
from . import _lang_rank as rank
from . import _textfit as tf
from ._mk_io import open_doc, save_doc

ARABIC_LETTER = re.compile("[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
LATIN_LETTER = re.compile("[A-Za-z]")
TIGHT_SCALE = 0.7
LETTERS = {"ar": ARABIC_LETTER, "en": LATIN_LETTER}


def detect_language(text: str) -> str:
    arabic, latin = len(ARABIC_LETTER.findall(text)), len(LATIN_LETTER.findall(text))
    return "ar" if arabic > latin else "en"


class Block:
    """A paragraph-like text block with the look needed to put the translation back."""

    def __init__(self, raw: dict):
        spans = [s for line in raw["lines"] for s in line["spans"] if s["text"].strip()]
        self.rect = pymupdf.Rect(raw["bbox"])
        self.text = " ".join(
            "".join(s["text"] for s in line["spans"]).strip() for line in raw["lines"]).strip()
        self.size = statistics.median(s["size"] for s in spans) if spans else 11.0
        first = spans[0] if spans else {"flags": 0, "color": 0, "font": ""}
        self.bold = bool(first["flags"] & 16) or "bold" in first["font"].lower()
        self.italic = bool(first["flags"] & 2) or "italic" in first["font"].lower()
        self.color = tuple(((first["color"] >> shift) & 255) / 255 for shift in (16, 8, 0))
        self.font = _family_of(first["font"])
        self.align = _alignment(raw)


def _family_of(name: str) -> str:
    lowered = name.lower()
    if "cour" in lowered or "mono" in lowered:
        return "courier"
    if "times" in lowered or "serif" in lowered and "sans" not in lowered or "georgia" in lowered:
        return "times"
    return "arial"


def _alignment(raw: dict) -> str:
    lines = [pymupdf.Rect(line["bbox"]) for line in raw["lines"]]
    box = pymupdf.Rect(raw["bbox"])
    if len(lines) < 2:
        return "left"
    centres = [(r.x0 + r.x1) / 2 for r in lines]
    if max(centres) - min(centres) < 2 and (max(r.x0 for r in lines) - min(r.x0 for r in lines)) > 4:
        return "center"
    return "left"


def text_blocks(page, source: str) -> list[Block]:
    letters = LETTERS.get(source, LATIN_LETTER)
    blocks = []
    for raw in page.get_text("dict")["blocks"]:
        if raw.get("type") != 0 or not raw.get("lines"):
            continue
        block = Block(raw)
        if letters.search(block.text) and len(block.text) > 1:
            blocks.append(block)
    return blocks


def _place(page, block: Block, text: str, target: str) -> float:
    rtl = target == "ar"
    align = "center" if block.align == "center" else ("right" if rtl else "left")
    rect = block.rect + (-0.5, -0.5, 0.5, 0.5)
    return tf.fit_text_in_rect(page, rect, text, size=block.size, color=block.color, font=block.font,
                               bold=block.bold, italic=block.italic, align=align, rtl=rtl)


def translate_page(page, source: str, target: str) -> dict:
    blocks = text_blocks(page, source)
    if not blocks:
        return {"blocks": 0, "tight": 0, "min_scale": 1.0}
    translated = [engine.translate_text(b.text, source, target) for b in blocks]
    for block in blocks:
        page.add_redact_annot(block.rect + (0.4, 0.4, -0.4, -0.4), fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE, text=0)
    scales = [_place(page, b, t, target) for b, t in zip(blocks, translated) if t.strip()]
    return {"blocks": len(blocks), "tight": sum(s < TIGHT_SCALE for s in scales), "min_scale": min(scales or [1.0])}


@tool("translate")
def translate(job: Job, args: dict) -> dict:
    source, target = str(args.get("source") or "auto").lower(), str(require(args, "target")).lower()
    doc = open_doc(args)
    if source == "auto":
        sample = " ".join(doc[i].get_text()[:2000] for i in range(min(doc.page_count, 3)))
        source = detect_language(sample)
    if not any(p.get_text().strip() for p in doc):
        raise ToolError("tool_failed", "This file has no text to translate. Use Recognize text on it first, then translate.")
    engine.route(source, target)
    stats = []
    try:
        for index, page in enumerate(doc):
            job.progress(index / doc.page_count, f"Translating page {index + 1} of {doc.page_count}")
            stats.append(translate_page(page, source, target))
    finally:
        engine.release_models()
    out = save_doc(doc, args, f"translated {target}", garbage=4, deflate=True)
    return result([out], source=source, target=target, blocks=sum(s["blocks"] for s in stats),
                  tight_blocks=sum(s["tight"] for s in stats),
                  smallest_scale=round(min(s["min_scale"] for s in stats), 2))


def _chosen_pages(args: dict, count: int) -> list[int]:
    spec = args.get("pages")
    if not spec:
        return list(range(count))
    if isinstance(spec, str):
        return parse_ranges(spec, count)
    pages = [int(p) for p in spec]
    bad = [p for p in pages if not 0 <= p < count]
    if bad:
        raise ToolError("bad_args", f"Page {bad[0] + 1} is outside this file, which has {count} pages.")
    return pages


def _document_text(doc, pages: list[int]) -> str:
    parts = []
    for index in pages:
        for block in doc[index].get_text("blocks", sort=True):
            if block[6] == 0 and block[4].strip():
                parts.append(block[4].strip())
    return "\n\n".join(parts)


@tool("summarize")
def summarize(job: Job, args: dict) -> dict:
    length = args.get("length", "medium")
    if length not in rank.SHARE:
        raise ToolError("bad_args", 'Summary length must be "short", "medium" or "long".')
    doc = open_doc(args)
    pages = _chosen_pages(args, doc.page_count)
    job.progress(0.2, "Reading the text")
    text = _document_text(doc, pages)
    src = Path(args["file"])
    doc.close()
    if not text.strip():
        raise ToolError("tool_failed", "This file has no text to summarize. Use Recognize text on it first.")
    job.progress(0.6, "Ranking sentences")
    summary = rank.summarise(text, length)
    if not summary["sentences"]:
        raise ToolError("tool_failed", "There was not enough readable text to summarize.")
    out = output_path(src, f"summary {length}", ".txt", args.get("out_dir"))
    out.write_text(summary["text"] + "\n", encoding="utf-8-sig")
    words = len(re.findall(r"\w+", text))
    return result([out], text=summary["text"], length=length, sentences=len(summary["sentences"]),
                  total_sentences=summary["total_sentences"], language=detect_language(text),
                  words_in=words, words_out=len(re.findall(r"\w+", summary["text"])))
