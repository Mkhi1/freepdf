"""Office-free conversion pieces: Office files to HTML, and right-to-left repair of pdf2docx output."""
import zipfile

from docx import Document

import samples_convert as S
from freepdf_engine.tools._html_docx import docx_to_html
from freepdf_engine.tools._html_sheet import sheet_to_html
from freepdf_engine.tools._html_slides import slides_to_html
from freepdf_engine.tools.docx_rtl import fix_rtl_docx


def document_xml(path) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read("word/document.xml").decode("utf-8")


def test_docx_html_keeps_text_tables_pictures_and_page_size(tmp_path):
    html = docx_to_html(S.make_docx(tmp_path / "e.docx", "english"))
    assert "Study Notes" in html and "<h1" in html and "@page{size:8.500in 11.000in" in html
    table = docx_to_html(S.make_docx(tmp_path / "t.docx", "table"))
    assert "<table" in table and all(cell in table for row in S.TABLE_ROWS for cell in row)
    assert "data:image/png;base64," in docx_to_html(S.make_docx(tmp_path / "i.docx", "images"))
    assert "column-count:2" in docx_to_html(S.make_docx(tmp_path / "c.docx", "columns"))


def test_docx_html_marks_arabic_paragraphs_right_to_left(tmp_path):
    html = docx_to_html(S.make_docx(tmp_path / "a.docx", "arabic"))
    assert 'dir="rtl"' in html and S.ARABIC_LINES[0] in html


def test_sheet_and_slides_html(tmp_path):
    sheet = sheet_to_html(S.make_xlsx(tmp_path / "g.xlsx"))
    assert "Grades" in sheet and "Amal" in sheet and ">91<" in sheet
    csv = tmp_path / "m.csv"
    csv.write_text("name,score\nسارة,9\n", encoding="utf-8-sig")
    assert 'dir="rtl">سارة' in sheet_to_html(csv)
    slides = slides_to_html(S.make_pptx(tmp_path / "d.pptx"))
    assert "Quarterly Review" in slides and "@page{size:720.00pt 540.00pt" in slides


def test_rtl_repair_marks_arabic_and_splits_glued_lines(tmp_path):
    doc = Document()
    para = doc.add_paragraph()
    para.add_run(S.ARABIC_LINES[0]).font.size = 254000  # 20pt, so szCs must follow
    para.add_run("English line")
    doc.add_paragraph("Only English here")
    path = tmp_path / "glued.docx"
    doc.save(str(path))
    assert fix_rtl_docx(path)
    xml = document_xml(path)
    assert "<w:bidi/>" in xml and "<w:rtl/>" in xml and "<w:szCs" in xml
    assert "<w:br/>" in xml  # the Arabic line no longer runs into the English one
    assert xml.count("<w:bidi/>") == 1  # the English paragraph is left alone
    assert Document(str(path)).paragraphs[1].text == "Only English here"


def test_rtl_repair_leaves_english_files_untouched(tmp_path):
    path = tmp_path / "en.docx"
    Document().save(str(path))
    before = path.read_bytes()
    assert not fix_rtl_docx(path)
    assert path.read_bytes() == before
