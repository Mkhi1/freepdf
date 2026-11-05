"""Builds the sample files the end-to-end tests feed to the app.

Run with the engine venv: python app/e2e/make_samples.py <out_dir>
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "engine" / "tests")]

import pymupdf as fitz  # noqa: E402

import samples_convert as conv  # noqa: E402
import samples_markup as markup  # noqa: E402
import samples_pages as pages  # noqa: E402


def locked_pdf(src: Path, dest: Path, password: str) -> Path:
    doc = fitz.open(src)
    doc.save(dest, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    doc.close()
    return dest


def edited_copy(src: Path, dest: Path) -> Path:
    doc = fitz.open(src)
    doc[0].insert_text((72, 400), "This sentence was added in version two.", fontsize=12)
    doc.save(dest)
    doc.close()
    return dest


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    study = pages.text_pdf(out / "Study notes.pdf", pages=6)
    pages.text_pdf(out / "Chapter two.pdf", pages=3, toc=False, links=False)
    pages.image_heavy_pdf(out / "Photos heavy.pdf", pages=3)
    pages.scanned_pdf(out / "Scanned page.pdf", "Cells are the basic unit of life", "الخلية هي وحدة الحياة")
    markup.make_arabic_pdf(out / "ملخص عربي.pdf")
    locked_pdf(study, out / "Locked notes.pdf", "secret1")
    edited_copy(study, out / "Study notes v2.pdf")
    conv.make_docx(out / "Essay.docx", "english")
    conv.make_pptx(out / "Slides.pptx")
    conv.make_xlsx(out / "Marks.xlsx")
    conv.make_jpeg(out / "Photo one.jpg")
    conv.photo_png(out / "Photo two.png")
    conv.photo_png(out / "Signature.png", size=(320, 110))
    conv.make_html(out / "Page.html", "article")
    (out / "notes.txt").write_text("not a pdf", encoding="utf-8")
    print(f"samples ready in {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
