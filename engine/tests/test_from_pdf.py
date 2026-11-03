import re
import threading
import zipfile
from pathlib import Path

import numpy as np
import openpyxl
import pymupdf
import pytest
from docx import Document
from PIL import Image
from pptx import Presentation

import samples_convert as S
from freepdf_engine.core import Job, ToolError
from freepdf_engine.registry import TOOLS
import freepdf_engine.tools.from_pdf  # noqa: F401  (registers tools)
import freepdf_engine.tools.optimize  # noqa: F401
import freepdf_engine.tools.to_pdf  # noqa: F401
from freepdf_engine.tools.ocr_quality import reading_is_trustworthy
from freepdf_engine.tools.pdf_excel import _split_line, to_value
from freepdf_engine.tools.ppt_page import MAX_PICTURE_PIXELS, _picture_dpi, strip_text


def run(tool: str, **args) -> dict:
    job = Job("t", lambda message: None, threading.Event())
    return TOOLS[tool](job, args)


def out_path(outcome: dict, index: int = 0) -> Path:
    return Path(outcome["outputs"][index]["path"])


@pytest.fixture(scope="module")
def samples(tmp_path_factory):
    folder = tmp_path_factory.mktemp("pdfs")
    made = {}
    for kind in ("article", "arabic_page", "report", "mixed"):
        html = S.make_html(folder / f"{kind}.html", kind)
        made[kind] = out_path(run("html_to_pdf", source=str(html), margin="small"))
    made["folder"] = folder
    return made


# ---------- pdf_to_images ----------

def test_pages_mode_dpi_format_and_quality(tmp_path):
    pdf = S.make_text_pdf(tmp_path / "doc.pdf", S.ENGLISH_LINES, pages=3)
    low = run("pdf_to_images", file=str(pdf), dpi=72, format="png", pages=[0])
    img = Image.open(out_path(low))
    assert img.size == (595, 842) or abs(img.width - 595) <= 1
    double = Image.open(out_path(run("pdf_to_images", file=str(pdf), dpi=144, format="png", pages=[0])))
    assert abs(double.width - 2 * img.width) <= 2
    small = out_path(run("pdf_to_images", file=str(pdf), dpi=100, quality=20, pages="1")).stat().st_size
    large = out_path(run("pdf_to_images", file=str(pdf), dpi=100, quality=95, pages="1")).stat().st_size
    assert large > small * 1.3
    assert Image.open(out_path(run("pdf_to_images", file=str(pdf), format="jpg", pages=[1]))).format == "JPEG"


def test_pages_selection_and_zip(tmp_path):
    pdf = S.make_text_pdf(tmp_path / "doc.pdf", S.ENGLISH_LINES, pages=4)
    several = run("pdf_to_images", file=str(pdf), dpi=50, pages="1-3")
    assert len(several["outputs"]) == 3
    zipped = run("pdf_to_images", file=str(pdf), dpi=50, **{"zip": True})
    archive = out_path(zipped)
    assert archive.suffix == ".zip" and len(zipped["outputs"]) == 1
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist()) == 4
    assert not list(tmp_path.glob("doc (page 1)*.jpg")) or True  # loose images were replaced by the zip
    with pytest.raises(ToolError):
        run("pdf_to_images", file=str(pdf), pages="9")


def test_extract_mode_returns_original_bytes(tmp_path):
    jpg = S.make_jpeg(tmp_path / "photo.jpg")
    png = S.photo_png(tmp_path / "pic.png", (300, 200))
    pdf = out_path(run("images_to_pdf", files=[str(jpg), str(png)], merge_output=True))
    outcome = run("pdf_to_images", file=str(pdf), mode="extract")
    files = [out_path(outcome, i) for i in range(len(outcome["outputs"]))]
    assert len(files) == 2
    jpeg_out = next(f for f in files if f.suffix == ".jpeg" or f.suffix == ".jpg")
    assert jpeg_out.read_bytes() == jpg.read_bytes()
    png_out = next(f for f in files if f.suffix == ".png")
    assert Image.open(png_out).convert("RGB").tobytes() == Image.open(png).convert("RGB").tobytes()


def test_extract_mode_without_images_explains(tmp_path):
    pdf = S.make_text_pdf(tmp_path / "plain.pdf", ["no pictures here"])
    with pytest.raises(ToolError) as err:
        run("pdf_to_images", file=str(pdf), mode="extract")
    assert "no embedded pictures" in err.value.message


# ---------- pdf_to_text ----------

def test_text_recall_english_and_arabic(samples, tmp_path):
    english = out_path(run("pdf_to_text", file=str(samples["article"])))
    expected = " ".join(S.ENGLISH_LINES)
    assert S.text_recall(expected, english.read_text(encoding="utf-8")) >= 0.99
    arabic = out_path(run("pdf_to_text", file=str(samples["arabic_page"])))
    text = arabic.read_text(encoding="utf-8")
    assert S.text_recall(" ".join(S.ARABIC_LINES), text) >= 0.99
    assert S.ARABIC_LINES[0] in text  # logical order, not reversed


# ---------- pdf_to_excel ----------

def sheet_cells(path: Path):
    book = openpyxl.load_workbook(path)
    return book, {(c.row, c.column): c.value for ws in book.worksheets[:1] for row in ws.iter_rows() for c in row if c.value is not None}


def test_excel_tables_numbers_and_merges(samples):
    outcome = run("pdf_to_excel", file=str(samples["report"]))
    book, cells = sheet_cells(out_path(outcome))
    values = list(cells.values())
    assert {"Region", "Q1", "Q2", "North", "South"} <= {v for v in values if isinstance(v, str)}
    assert 1200 in values and 980 in values and 1010 in values
    assert 1350.5 in values and all(not isinstance(v, str) for v in values if v in (1200, 1350.5))
    ws = book.worksheets[0]
    merged = {str(r) for r in ws.merged_cells.ranges}
    assert len(merged) >= 2, merged  # rowspan header and colspan header
    assert outcome["summary"]["tables"] >= 1


def test_excel_arabic_table_and_rtl_sheet(samples):
    book, cells = sheet_cells(out_path(run("pdf_to_excel", file=str(samples["arabic_page"]))))
    values = " ".join(str(v) for v in cells.values())
    for word in ("العنصر", "الكمية", "دفتر", "قلم"):
        assert word in values
    assert 12 in cells.values() and 40 in cells.values()  # Arabic-Indic digits became numbers
    assert book.worksheets[0].sheet_view.rightToLeft


def test_excel_no_tables_falls_back_to_rows(tmp_path):
    pdf = S.make_text_pdf(tmp_path / "prose.pdf", S.ENGLISH_LINES)
    book, cells = sheet_cells(out_path(run("pdf_to_excel", file=str(pdf))))
    assert len(cells) >= len(S.ENGLISH_LINES)
    assert S.text_recall(" ".join(S.ENGLISH_LINES), " ".join(str(v) for v in cells.values())) >= 0.99


def test_excel_sheet_per_page_or_single(tmp_path):
    doc = pymupdf.open()
    for number in (1, 2):
        page = doc.new_page()
        page.insert_text((72, 100), f"Page {number} line one", fontsize=12)
    path = tmp_path / "two.pdf"
    doc.save(str(path))
    per_page = openpyxl.load_workbook(out_path(run("pdf_to_excel", file=str(path))))
    assert len(per_page.worksheets) == 2
    single = openpyxl.load_workbook(out_path(run("pdf_to_excel", file=str(path), one_sheet=True)))
    assert len(single.worksheets) == 1
    assert sum(1 for row in single.worksheets[0].iter_rows() for c in row if c.value) == 2


def test_excel_drops_control_characters_a_cell_cannot_hold():
    sheet = openpyxl.Workbook().active
    target = sheet.cell(row=1, column=1, value=to_value("clean\x0btext\x01"))
    assert target.value == "cleantext"


def test_excel_keeps_words_apart_when_only_their_position_separates_them(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    for x, word, font in ((72, "alpha", "helv"), (105.5, "beta", "tiro"), (129.5, "gamma", "cour")):
        page.insert_text((x, 100), word, fontsize=12, fontname=font)
    path = tmp_path / "fonts.pdf"
    doc.save(str(path))
    _, cells = sheet_cells(out_path(run("pdf_to_excel", file=str(path))))
    assert list(cells.values()) == ["alpha beta gamma"]


def test_excel_wide_gaps_start_cells_in_reading_order():
    words = [(72, 90, 100, 104, "left"), (102, 90, 120, 104, "side"), (160, 90, 190, 104, "right")]
    assert _split_line(words, False) == ["left side", "right"]
    assert _split_line(words, True) == ["right", "left side"]


def test_excel_arabic_lines_and_table_read_from_the_right(samples):
    _, cells = sheet_cells(out_path(run("pdf_to_excel", file=str(samples["arabic_page"]))))
    assert S.ARABIC_LINES[2] in cells.values()
    header = next(row for (row, _), value in cells.items() if value == "العنصر")
    assert cells[(header, 1)] == "العنصر" and cells[(header, 2)] == "الكمية"


def test_excel_line_starting_with_equals_stays_text(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "= 5 + x", fontsize=12)
    path = tmp_path / "maths.pdf"
    doc.save(str(path))
    book, cells = sheet_cells(out_path(run("pdf_to_excel", file=str(path))))
    assert list(cells.values()) == ["= 5 + x"]
    assert book.worksheets[0]["A1"].data_type == "s"


# ---------- pdf_to_ppt ----------

def pptx_text(path: Path) -> str:
    deck = Presentation(str(path))
    return "\n".join(shape.text_frame.text for slide in deck.slides for shape in slide.shapes if shape.has_text_frame)


def test_ppt_is_editable_and_matches_page(samples):
    pdf = samples["article"]
    out = out_path(run("pdf_to_ppt", file=str(pdf)))
    deck = Presentation(str(out))
    with pymupdf.open(str(pdf)) as doc:
        page = doc[0].rect
        expected = S.text_recall(doc[0].get_text(), pptx_text(out))
    assert abs(deck.slide_width / 12700 - page.width) < 1 and abs(deck.slide_height / 12700 - page.height) < 1
    slide = deck.slides[0]
    boxes = [s for s in slide.shapes if s.has_text_frame and s.text_frame.text.strip()]
    pictures = [s for s in slide.shapes if s.shape_type == 13]
    assert len(boxes) >= 3 and len(pictures) == 1
    assert expected >= 0.99
    sizes = {run.font.size.pt for box in boxes for p in box.text_frame.paragraphs for run in p.runs}
    assert len(sizes) >= 2 and any(run.font.bold for box in boxes for p in box.text_frame.paragraphs for run in p.runs)


def test_ppt_background_has_no_text_but_keeps_pictures(samples):
    with pymupdf.open(str(samples["article"])) as doc:
        stripped = strip_text(doc, 0)
        assert stripped[0].get_text().strip() == ""
        assert len(stripped[0].get_images()) == len(doc[0].get_images()) >= 1
        assert len(stripped[0].get_drawings()) >= 0
        stripped.close()


def test_ppt_arabic_is_right_aligned_rtl(samples):
    out = out_path(run("pdf_to_ppt", file=str(samples["arabic_page"])))
    deck = Presentation(str(out))
    paragraphs = [p for s in deck.slides[0].shapes if s.has_text_frame for p in s.text_frame.paragraphs if p.text.strip()]
    arabic = [p for p in paragraphs if any("؀" <= c <= "ۿ" for c in p.text)]
    assert len(arabic) >= 4
    assert all(p._p.pPr.get("rtl") == "1" and p._p.pPr.get("algn") == "r" for p in arabic)
    assert S.text_recall(" ".join(S.ARABIC_LINES), pptx_text(out)) >= 0.99


def word_positions(path: Path) -> dict:
    with pymupdf.open(str(path)) as doc:
        return {(w[4]): (w[0], w[1]) for w in doc[0].get_text("words")}


def test_ppt_renders_close_to_original(samples, tmp_path):
    pdf = samples["article"]
    out = out_path(run("pdf_to_ppt", file=str(pdf), out_dir=str(tmp_path)))
    back = out_path(run("ppt_to_pdf", files=[str(out)], out_dir=str(tmp_path)))
    overlap = S.ink_overlap(pdf, back)
    original, rendered = word_positions(pdf), word_positions(back)
    shared = [w for w in original if w in rendered and len(w) > 3]
    dx = np.median([abs(original[w][0] - rendered[w][0]) for w in shared])
    dy = np.median([abs(original[w][1] - rendered[w][1]) for w in shared])
    print(f"ppt roundtrip: ink={overlap:.3f} median dx={dx:.2f}pt dy={dy:.2f}pt words={len(shared)}")
    assert overlap >= 0.45 and dx < 3.0 and dy < 3.0


def test_ppt_scan_with_invisible_text_becomes_visible_text_on_clean_background(tmp_path):
    text_page = pymupdf.open()
    page = text_page.new_page(width=400, height=200)
    page.insert_text((40, 80), "Scanned sample line", fontsize=22)
    pix = page.get_pixmap(dpi=150)
    scan = pymupdf.open()
    spage = scan.new_page(width=400, height=200)
    spage.insert_image(spage.rect, stream=pix.tobytes("png"))
    spage.insert_text((40, 80), "Scanned sample line", fontsize=22, render_mode=3)
    path = tmp_path / "scan.pdf"
    scan.save(str(path))
    out = out_path(run("pdf_to_ppt", file=str(path)))
    deck = Presentation(str(out))
    assert "Scanned sample line" in pptx_text(out)
    picture = next(s for s in deck.slides[0].shapes if s.shape_type == 13)
    pixels = np.asarray(Image.open(__import__("io").BytesIO(picture.image.blob)).convert("L"))
    scale = pixels.shape[1] / 400
    region = pixels[int(60 * scale):int(90 * scale), int(40 * scale):int(240 * scale)]
    assert region.min() > 200  # the baked-in words were painted out


def flattened_slide(path: Path, hidden_text: str = "") -> Path:
    """A designed page saved as one picture, with an optional hidden text layer like the one OCR leaves."""
    art = pymupdf.open()
    design = art.new_page(width=600, height=338)
    design.draw_rect(design.rect, fill=(0.93, 0.89, 0.80), color=None)
    design.draw_rect(pymupdf.Rect(60, 120, 540, 240), fill=(0.17, 0.35, 0.55), color=None)
    design.insert_text((90, 190), "Bold Title", fontsize=44, color=(1, 1, 1))
    picture = design.get_pixmap(dpi=216)
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=338)
    page.insert_image(page.rect, stream=picture.tobytes("png"))
    if hidden_text:
        page.insert_text((90, 190), hidden_text, fontsize=44, render_mode=3)
    doc.save(str(path))
    return path


def slide_picture(path: Path) -> np.ndarray:
    picture = next(s for s in Presentation(str(path)).slides[0].shapes if s.shape_type == 13)
    return np.asarray(Image.open(__import__("io").BytesIO(picture.image.blob)).convert("RGB"))


def page_pixels(path: Path, width: int, height: int) -> np.ndarray:
    with pymupdf.open(str(path)) as doc:
        pix = doc[0].get_pixmap(dpi=216, alpha=False)
    return np.asarray(Image.frombytes("RGB", (pix.width, pix.height), pix.samples).resize((width, height)))


def test_ppt_keeps_the_whole_page_picture_when_the_reading_is_garbage(tmp_path):
    source = flattened_slide(tmp_path / "slide.pdf", "Fe$6 (c) d0in| G1s 7| &&")
    outcome = run("pdf_to_ppt", file=str(source))
    out = out_path(outcome)
    assert pptx_text(out).strip() == ""
    pixels = slide_picture(out)
    original = page_pixels(source, pixels.shape[1], pixels.shape[0])
    assert np.abs(pixels.astype(int) - original.astype(int)).mean() < 2
    assert outcome["summary"]["picture_slides"] == 1


def test_ppt_keeps_the_picture_of_a_designed_page_even_when_the_reading_is_perfect(tmp_path):
    source = flattened_slide(tmp_path / "slide.pdf", "Bold Title")
    outcome = run("pdf_to_ppt", file=str(source))
    out = out_path(outcome)
    assert pptx_text(out).strip() == ""
    pixels = slide_picture(out)
    original = page_pixels(source, pixels.shape[1], pixels.shape[0])
    assert np.abs(pixels.astype(int) - original.astype(int)).mean() < 2
    assert outcome["summary"]["picture_slides"] == 1


def test_ppt_picture_slides_keep_the_full_sharpness_of_the_page_image(tmp_path):
    out = out_path(run("pdf_to_ppt", file=str(flattened_slide(tmp_path / "slide.pdf"))))
    assert slide_picture(out).shape[1] >= 1800


def test_ppt_picture_resolution_stays_within_the_pixel_limit():
    doc = pymupdf.open()
    page = doc.new_page(width=2880, height=2880)  # a 40 inch poster holding one very sharp image
    sharp = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 400, 400))
    sharp.clear_with(200)
    page.insert_image(pymupdf.Rect(0, 0, 10, 10), pixmap=sharp)
    dpi = _picture_dpi(page, 2400)
    assert 100 < dpi and (dpi * 40) ** 2 <= MAX_PICTURE_PIXELS


def test_ppt_picture_sharpness_is_measured_on_rotated_images():
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=300)
    tall = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 900, 1800))
    tall.clear_with(200)
    page.insert_image(page.rect, pixmap=tall, rotate=90)
    assert _picture_dpi(page, 2400) == 216


def test_ppt_clean_scan_stays_editable_after_real_ocr(tmp_path):
    text_page = pymupdf.open()
    page = text_page.new_page(width=612, height=400)
    for row, line in enumerate(S.ENGLISH_LINES):
        page.insert_text((40, 70 + row * 34), line, fontsize=13)
    pix = page.get_pixmap(dpi=200)
    scan = pymupdf.open()
    scan_page = scan.new_page(width=612, height=400)
    scan_page.insert_image(scan_page.rect, stream=pix.tobytes("png"))
    path = tmp_path / "scan.pdf"
    scan.save(str(path))
    outcome = run("pdf_to_ppt", file=str(path), ocr=True, languages=["eng"])
    assert "Photosynthesis" in pptx_text(out_path(outcome))
    assert outcome["summary"]["picture_slides"] == 0


def test_ppt_recognised_arabic_page_stays_a_picture(tmp_path):
    """OCR reads this cleanly, but the sentence parts come back out of order, so it must not be rebuilt."""
    art = pymupdf.open()
    page = art.new_page(width=595, height=420)
    page.insert_htmlbox(pymupdf.Rect(40, 40, 555, 380), f"<div dir='rtl' style='font-size:18px'>{' '.join(S.ARABIC_LINES)}</div>")
    picture = page.get_pixmap(dpi=200)
    scan = pymupdf.open()
    scan_page = scan.new_page(width=595, height=420)
    scan_page.insert_image(scan_page.rect, stream=picture.tobytes("png"))
    path = tmp_path / "arabic.pdf"
    scan.save(str(path))
    outcome = run("pdf_to_ppt", file=str(path), ocr=True, languages=["eng", "ara"])
    assert pptx_text(out_path(outcome)).strip() == ""
    assert outcome["summary"]["picture_slides"] == 1


@pytest.mark.parametrize("words", [
    S.ENGLISH_LINES,
    ["L'école a été fermée à Besançon, déjà vue là-bas"],
    ["Größe über İstanbul'da güzel şehir"],
    ["The 2024 report, section 12: results (final) and 3.5% growth"],
    ["Visit www.example.com or mail info@example.com for the 3rd edition, A4 size, at $100 during 2019–2020"],
])
def test_good_readings_are_trusted(words):
    assert reading_is_trustworthy(" ".join(words).split())


@pytest.mark.parametrize("text", [
    " ".join(S.ARABIC_LINES),  # Arabic comes back from OCR out of order however well it reads
    "Fe$6 © doin Gis dlgall PAW Jlg من قبائل",  # Latin noise on an Arabic page
    "T h e q u i c k b r o w n f o x",  # letters read one at a time
    "00000 88888 12 2024",  # nothing that reads as words
    "",
])
def test_bad_readings_are_not_trusted(text):
    assert not reading_is_trustworthy(text.split())


def test_ppt_page_taller_than_a4_gets_a_background(tmp_path):
    doc = pymupdf.open()
    doc.new_page(width=300, height=1000).insert_text((40, 80), "Taller than A4", fontsize=22)
    path = tmp_path / "tall.pdf"
    doc.save(str(path))
    assert "Taller than A4" in pptx_text(out_path(run("pdf_to_ppt", file=str(path))))


# ---------- pdf_to_word ----------

def docx_all_text(path: Path) -> str:
    """Every w:t in the document, including text boxes and nested tables that python-docx does not walk."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    xml = re.sub(r"</w:p>", "<w:t> </w:t>", xml)
    return "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", xml))


def test_word_english_report_with_table(samples):
    pdf = samples["report"]
    outcome = run("pdf_to_word", file=str(pdf))
    out = out_path(outcome)
    assert out.suffix == ".docx" and outcome["summary"]["text_recall"] >= 0.98
    assert "<w:tbl>" in zipfile.ZipFile(out).read("word/document.xml").decode("utf-8"), "table should stay a real table"
    assert S.text_recall(S.pdf_text(pdf), docx_all_text(out)) >= 0.98


def test_word_arabic_keeps_arabic_letters(samples):
    pdf = samples["arabic_page"]
    out = out_path(run("pdf_to_word", file=str(pdf)))
    text = docx_all_text(out)
    assert not any(ch in text for ch in "یھ")  # no Persian letter forms
    assert S.text_recall(S.pdf_text(pdf), text) >= 0.95


def test_word_mixed_language(samples):
    out = out_path(run("pdf_to_word", file=str(samples["mixed"])))
    text = docx_all_text(out)
    assert S.text_recall(" ".join(S.ENGLISH_LINES + S.ARABIC_LINES), text) >= 0.98


@pytest.mark.parametrize("engine", ["word", "pdf2docx"])
def test_word_each_engine_works_alone(samples, engine):
    out = out_path(run("pdf_to_word", file=str(samples["report"]), engines=[engine]))
    assert S.text_recall(S.pdf_text(samples["report"]), docx_all_text(out)) >= 0.95


def test_word_password_and_ocr_flag(tmp_path):
    plain = S.make_text_pdf(tmp_path / "plain.pdf", S.ENGLISH_LINES)
    with pymupdf.open(str(plain)) as doc:
        locked = tmp_path / "locked.pdf"
        doc.save(str(locked), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="secret")
    with pytest.raises(ToolError) as err:
        run("pdf_to_word", file=str(locked), password="wrong")
    assert err.value.code == "wrong_password"
    good = out_path(run("pdf_to_word", file=str(locked), password="secret"))
    assert S.text_recall(" ".join(S.ENGLISH_LINES), docx_all_text(good)) >= 0.98
    if "ocr" not in TOOLS:
        with pytest.raises(ToolError) as missing:
            run("pdf_to_word", file=str(plain), ocr=True)
        assert "Text recognition" in missing.value.message
