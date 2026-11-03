"""Generated documents and quality metrics for the conversion tests."""
import io
import re
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
import pymupdf
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from openpyxl import Workbook
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.util import Inches as PInches
from pptx.util import Pt as PPt

ARABIC_LINES = [
    "مرحبا بكم في تطبيق الملفات المجاني",
    "هذا المستند يحتوي على نص عربي لاختبار جودة التحويل",
    "التعلم المستمر هو مفتاح النجاح في الدراسة والعمل",
    "تم إنشاء هذا الملف لقياس دقة استخراج النص من ملفات",
]
ENGLISH_LINES = [
    "The quick brown fox jumps over the lazy dog near the riverbank.",
    "Photosynthesis converts light energy into chemical energy stored in glucose.",
    "Newton's second law states that force equals mass times acceleration.",
    "A free offline application should convert documents with high fidelity.",
]
TABLE_ROWS = [["Item", "Quantity", "Price"], ["Notebook", "12", "3.50"], ["Pencil", "40", "0.75"], ["Ruler", "7", "1.20"]]
ARABIC_FONT = "Arial"


def photo_png(path: Path, size=(480, 300)) -> Path:
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for x in range(size[0]):
        draw.line([(x, 0), (x, size[1])], fill=(x * 255 // size[0], 90, 255 - x * 255 // size[0]))
    draw.ellipse([60, 60, 220, 220], fill=(250, 220, 40), outline=(0, 0, 0), width=4)
    draw.rectangle([260, 90, 420, 240], fill=(30, 160, 80), outline=(255, 255, 255), width=5)
    img.save(path)
    return path


def _set_rtl(paragraph) -> None:
    props = paragraph._p.get_or_add_pPr()
    props.append(OxmlElement("w:bidi"))
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT


def _arabic_run(paragraph, text: str):
    run = paragraph.add_run(text)
    run.font.size = Pt(14)
    run.font.name = ARABIC_FONT
    props = run._r.get_or_add_rPr()
    props.append(OxmlElement("w:rtl"))
    fonts = props.find(qn("w:rFonts"))
    fonts.set(qn("w:cs"), ARABIC_FONT)
    return run


def make_docx(path: Path, kind: str) -> Path:
    doc = Document()
    if kind == "english":
        doc.add_heading("Study Notes", 1)
        for _ in range(3):
            for line in ENGLISH_LINES:
                doc.add_paragraph(line)
    elif kind == "arabic":
        for _ in range(3):
            for line in ARABIC_LINES:
                para = doc.add_paragraph()
                _set_rtl(para)
                _arabic_run(para, line)
    elif kind == "table":
        doc.add_paragraph("Inventory table")
        table = doc.add_table(rows=len(TABLE_ROWS), cols=3)
        table.style = "Table Grid"
        for r, row in enumerate(TABLE_ROWS):
            for c, value in enumerate(row):
                table.cell(r, c).text = value
        doc.add_paragraph("End of table.")
    elif kind == "images":
        doc.add_paragraph(ENGLISH_LINES[0])
        image = photo_png(path.with_suffix(".png"))
        doc.add_picture(str(image), width=Inches(4.5))
        doc.add_paragraph(ENGLISH_LINES[1])
    elif kind == "columns":
        cols = doc.sections[0]._sectPr.find(qn("w:cols"))
        cols.set(qn("w:num"), "2")
        cols.set(qn("w:space"), "720")
        for i in range(40):
            doc.add_paragraph(f"Column paragraph {i + 1}. " + ENGLISH_LINES[i % 4])
    doc.save(str(path))
    return path


def make_pptx(path: Path) -> Path:
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "Quarterly Review"
    box = slide.shapes.add_textbox(PInches(1), PInches(2), PInches(8), PInches(1.5))
    box.text_frame.text = "Revenue grew steadily across all regions"
    box.text_frame.paragraphs[0].runs[0].font.size = PPt(24)
    deck.save(str(path))
    return path


def make_xlsx(path: Path) -> Path:
    book = Workbook()
    sheet = book.active
    sheet.title = "Grades"
    for row in [["Student", "Score", "Passed"], ["Amal", 91, "yes"], ["Omar", 78, "yes"], ["Lina", 55, "no"]]:
        sheet.append(row)
    book.save(str(path))
    return path


def make_jpeg(path: Path, size=(640, 400), exif_orientation: int | None = None) -> Path:
    img = Image.open(photo_png(path.with_suffix(".src.png"), size)).convert("RGB")
    ImageDraw.Draw(img).rectangle([0, 0, 60, 60], fill=(255, 0, 0))  # red marker, top-left corner
    exif = Image.Exif()
    if exif_orientation:
        exif[274] = exif_orientation
    img.save(path, "JPEG", quality=83, exif=exif)
    return path


def make_text_pdf(path: Path, lines: list[str], pages: int = 1) -> Path:
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        for i, line in enumerate(lines):
            page.insert_text((72, 100 + i * 26), line, fontsize=14)
    doc.save(str(path))
    doc.close()
    return path


def pdf_text(path: Path) -> str:
    with pymupdf.open(str(path)) as doc:
        return "\n".join(page.get_text() for page in doc)


def _canon(word: str) -> str:
    word = unicodedata.normalize("NFKC", word)
    word = word.replace("لا", "ال")  # PDF extraction may swap the lam-alef pair
    word = "".join(ch for ch in word if unicodedata.category(ch)[0] in "LN")
    return min(word, word[::-1])  # same word whether stored in visual or logical order


def words(text: str) -> Counter:
    return Counter(w for w in (_canon(t) for t in re.split(r"\s+", text)) if w)


def text_recall(reference: str, candidate: str) -> float:
    """Share of the reference words found in the candidate (order-insensitive, bidi-safe)."""
    ref, cand = words(reference), words(candidate)
    total = sum(ref.values())
    return sum((ref & cand).values()) / total if total else 1.0


def render_gray(path: Path, page_number: int = 0, size=(120, 160)) -> np.ndarray:
    with pymupdf.open(str(path)) as doc:
        pix = doc[page_number].get_pixmap(dpi=40, colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples).resize(size, Image.BILINEAR)
    return np.asarray(img, dtype=np.float32) / 255.0


def render_similarity(a: Path, b: Path) -> float:
    """1 minus the mean absolute difference of blurred greyscale renders of page 1 (1.0 is identical)."""
    first, second = render_gray(a), render_gray(b)
    blur = lambda m: np.asarray(Image.fromarray((m * 255).astype("uint8")).resize((60, 80), Image.BOX), dtype=np.float32) / 255
    return float(1.0 - np.abs(blur(first) - blur(second)).mean())


def image_bytes_of(path: Path) -> list[bytes]:
    out = []
    with pymupdf.open(str(path)) as doc:
        for page in doc:
            for img in page.get_images(full=True):
                out.append(doc.xref_stream_raw(img[0]))
    return out


def png_size(data: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(data)).size


def ink_overlap(a: Path, b: Path, page_number: int = 0) -> float:
    """Overlap of the dark pixels of two page renders (intersection over union, 1.0 is identical)."""
    ink = lambda path: 1.0 - render_gray(path, page_number, size=(300, 400))
    first, second = ink(a), ink(b)
    return float(np.minimum(first, second).sum() / max(np.maximum(first, second).sum(), 1e-6))


HTML_STYLE = "<style>body{font-family:Arial;font-size:13px;margin:30px} h1{color:#1a4f8b} h2{color:#8b1a1a} th{background:#dde8f5} td,th{border:1px solid #444;padding:4px}</style>"


def make_html(path: Path, kind: str) -> Path:
    photo = photo_png(path.with_suffix(".jpg.png"), (360, 200)).name
    if kind == "article":
        body = (f"<h1>Renewable Energy Overview</h1><div style='column-count:2;column-gap:30px'>"
                + "".join(f"<p><b>Section {i}.</b> <i>{ENGLISH_LINES[i % 4]}</i> {ENGLISH_LINES[(i + 1) % 4]}</p>" for i in range(1, 9))
                + "<ul><li>Solar power</li><li>Wind power</li><li>Hydro power</li></ul>"
                + f"<img src='{photo}' width='260'></div>")
    elif kind == "arabic_page":
        body = ("<div dir='rtl' style='font-size:16px'><h1>" + ARABIC_LINES[0] + "</h1>"
                + "".join(f"<p>{line}</p>" for line in ARABIC_LINES * 2)
                + "<table dir='rtl'><tr><th>العنصر</th><th>الكمية</th></tr><tr><td>دفتر</td><td>١٢</td></tr><tr><td>قلم</td><td>٤٠</td></tr></table></div>")
    elif kind == "report":
        body = ("<h1>Sales Report</h1><table style='border-collapse:collapse'>"
                "<tr><th rowspan='2'>Region</th><th colspan='2'>2025</th></tr><tr><th>Q1</th><th>Q2</th></tr>"
                "<tr><td>North</td><td>1200</td><td>1350.50</td></tr><tr><td>South</td><td>980</td><td>1010</td></tr></table>"
                f"<h2>Notes</h2><p>{ENGLISH_LINES[3]}</p><img src='{photo}' width='300'>")
    else:  # mixed
        body = ("<h1>Mixed language notes</h1>"
                + "".join(f"<p>{ENGLISH_LINES[i]}</p><p dir='rtl'>{ARABIC_LINES[i]}</p>" for i in range(4)))
    path.write_text(f"<html><head><meta charset='utf-8'>{HTML_STYLE}</head><body>{body}</body></html>", encoding="utf-8")
    return path
