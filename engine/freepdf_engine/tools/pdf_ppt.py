"""PDF to editable PowerPoint: text-free page picture as the background, real text boxes on top."""
import io
import shutil
from pathlib import Path

import pymupdf
from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from ..convert_util import open_pdf, scratch_dir
from ..core import Job, ToolError, output_path, require, result
from ..registry import tool
from .ocr_quality import reading_is_trustworthy
from .pdf_ocr import ocr_input
from .ppt_page import (
    ARABIC, MAX_OTHER_INK, Block, Run, background_bytes, has_only_invisible_text, other_ink_share, page_picture, text_blocks,
)

EMU_PER_POINT = 12700
MAX_SLIDE_POINTS = 4000.0
WIDTH_SLACK = 1.06  # boxes are a little wider than the original text so a substituted font does not wrap
TOP_NUDGE = 0.0  # fraction of a line height; measured against PowerPoint renders in the tests
ALIGN = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}


def _emu(points: float) -> Emu:
    return Emu(int(round(points * EMU_PER_POINT)))


def _style_run(run, spec: Run, scale: float) -> None:
    run.font.size = Pt(max(spec.size * scale, 1.0))
    run.font.bold = spec.bold
    run.font.italic = spec.italic
    run.font.color.rgb = RGBColor((spec.color >> 16) & 255, (spec.color >> 8) & 255, spec.color & 255)
    run.font.name = spec.font
    props = run._r.get_or_add_rPr()
    if ARABIC.search(spec.text):
        props.set("lang", "ar-SA")
        cs = props.find(qn("a:cs"))
        if cs is None:
            cs = etree.SubElement(props, qn("a:cs"))
        cs.set("typeface", spec.font if spec.font else "Arial")


def _fill_paragraph(paragraph, block: Block, scale: float) -> None:
    for number, line in enumerate(block.lines):
        if number:
            paragraph.add_line_break()
        for spec in line:
            run = paragraph.add_run()
            run.text = spec.text
            _style_run(run, spec, scale)
    paragraph.alignment = ALIGN[block.align]
    if len(block.lines) > 1:
        paragraph.line_spacing = Pt(block.pitch * scale)
    if block.rtl:
        paragraph._p.get_or_add_pPr().set("rtl", "1")


def _geometry(block: Block, scale: float, dx: float, dy: float) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = block.bbox
    width = (x1 - x0) * WIDTH_SLACK + 2
    extra = width - (x1 - x0)
    if block.align == "right":
        left = x0 - extra
    elif block.align == "center":
        left = x0 - extra / 2
    else:
        left = x0 - 1
    top = y0 + TOP_NUDGE * block.pitch
    return left * scale + dx, top * scale + dy, width * scale, (y1 - y0) * scale


def add_block(slide, block: Block, scale: float, dx: float, dy: float) -> None:
    left, top, width, height = _geometry(block, scale, dx, dy)
    box = slide.shapes.add_textbox(_emu(left), _emu(top), _emu(width), _emu(max(height, 4)))
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = MSO_ANCHOR.TOP
    frame.auto_size = None
    _fill_paragraph(frame.paragraphs[0], block, scale)
    if block.angle:
        box.rotation = -block.angle


def _slide_frame(doc: pymupdf.Document) -> tuple[float, float, float]:
    first = doc[0].rect
    shrink = min(1.0, MAX_SLIDE_POINTS / max(first.width, first.height))
    return first.width * shrink, first.height * shrink, shrink


def _fit(page_rect: pymupdf.Rect, width: float, height: float, base: float) -> tuple[float, float, float]:
    scale = min(width / page_rect.width, height / page_rect.height)
    return scale, (width - page_rect.width * scale) / 2, (height - page_rect.height * scale) / 2


def _keep_picture(page: pymupdf.Page) -> bool:
    """True when a page known only through hidden OCR text cannot be rebuilt without damaging it.

    Rebuilding erases the picture under each recognised line, so it needs a good left-to-right reading of a page
    that holds nothing but text. Photos, cards and drawings get painted over, and OCR finds phantom text in them.
    """
    if not has_only_invisible_text(page):
        return False
    return not reading_is_trustworthy(w[4] for w in page.get_text("words")) or other_ink_share(page) > MAX_OTHER_INK


def build_presentation(job: Job, doc: pymupdf.Document) -> tuple[Presentation, int]:
    """The deck, and how many scanned slides stayed as pictures instead of becoming editable text."""
    width, height, base = _slide_frame(doc)
    deck = Presentation()
    deck.slide_width, deck.slide_height = _emu(width), _emu(height)
    blank = deck.slide_layouts[6]
    picture_slides = 0
    for index in range(doc.page_count):
        job.progress(0.1 + 0.85 * index / doc.page_count, f"Slide {index + 1} of {doc.page_count}")
        page = doc[index]
        scale, dx, dy = _fit(page.rect, width, height, base)
        slide = deck.slides.add_slide(blank)
        keep = _keep_picture(page)
        blocks = [] if keep else text_blocks(page)
        data, _ = background_bytes(doc, index) if blocks else page_picture(page)
        slide.shapes.add_picture(io.BytesIO(data), _emu(dx), _emu(dy), _emu(page.rect.width * scale), _emu(page.rect.height * scale))
        for block in blocks:
            add_block(slide, block, scale, dx, dy)
        picture_slides += keep
    return deck, picture_slides


@tool("pdf_to_ppt")
def pdf_to_ppt(job: Job, args: dict) -> dict:
    source = Path(require(args, "file"))
    doc = open_pdf(str(source), args.get("password"))
    work_dir = scratch_dir()
    try:
        prepared = ocr_input(job, source, args, work_dir)
        if prepared != source:
            doc.close()
            doc = open_pdf(str(prepared))
        if doc.page_count == 0:
            raise ToolError("bad_args", "This PDF has no pages.")
        deck, picture_slides = build_presentation(job, doc)
        target = output_path(source, "", ".pptx", args.get("out_dir"))
        deck.save(str(target))
        slides = doc.page_count
    finally:
        doc.close()
        shutil.rmtree(work_dir, ignore_errors=True)
    job.progress(1.0, "Done")
    return result([target], slides=slides, picture_slides=picture_slides)
