"""Editable Word file from recognised text. Scans have no real layout for a converter to read."""
from pathlib import Path

import pymupdf
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from .docx_text import is_mostly_arabic


def _mark_rtl(paragraph) -> None:
    # In a right-to-left paragraph the default alignment is already the right edge.
    paragraph._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
    for run in paragraph.runs:
        props = run._r.get_or_add_rPr()
        props.append(OxmlElement("w:rtl"))
        lang = OxmlElement("w:lang")
        lang.set(qn("w:bidi"), "ar-SA")
        props.append(lang)


def _paragraphs(page: pymupdf.Page) -> list[str]:
    found = []
    for block in page.get_text("blocks", sort=True):
        if block[6] != 0:
            continue
        text = " ".join(block[4].split())
        if text:
            found.append(text)
    return found


def write_docx_from_text(source: Path, dest: Path) -> None:
    """One paragraph per recognised text block, one page break between pages."""
    document = Document()
    with pymupdf.open(str(source)) as pdf:
        for number, page in enumerate(pdf):
            if number:
                document.add_page_break()
            for text in _paragraphs(page):
                paragraph = document.add_paragraph(text)
                if is_mostly_arabic(text):
                    _mark_rtl(paragraph)
    document.save(str(dest))
