from pathlib import Path

import pytest
from samples_pages import (
    call, damaged_pdfs, difference, image_heavy_pdf, page_text, pymupdf, render, scanned_pdf, text_pdf,
)

from freepdf_engine.core import ToolError, resource_dir
from freepdf_engine.tools.optimize import find_ghostscript, pdfa_part

ARABIC = "مرحبا بالعالم هذا اختبار"
HAS_TESSDATA = all((resource_dir("tessdata") / f"{c}.traineddata").is_file() for c in ("eng", "ara"))


def only(res) -> Path:
    [out] = res["outputs"]
    return Path(out["path"])


@pytest.fixture(scope="module")
def heavy(tmp_path_factory) -> Path:
    return image_heavy_pdf(tmp_path_factory.mktemp("heavy") / "photos.pdf", pages=3)


def test_compress_levels_really_differ_and_text_stays_text(heavy, tmp_path):
    original = heavy.stat().st_size
    sizes, diffs = {}, {}
    for level in ("less", "recommended", "extreme"):
        res = call("compress", {"file": str(heavy), "level": level, "out_dir": str(tmp_path / level)})
        out = only(res)
        sizes[level] = out.stat().st_size
        assert res["summary"]["before"] == original and res["summary"]["after"] == sizes[level]
        assert res["summary"]["percent"] == pytest.approx(100 * (original - sizes[level]) / original, abs=0.1)
        with pymupdf.open(str(out)) as doc:
            assert len(doc) == 3
            assert f"quokka{2}" in doc[1].get_text()
            assert doc[1].search_for("quokka2")
        diffs[level] = difference(render(heavy, 0), render(out, 0))
    assert sizes["less"] < original * 0.5
    assert sizes["extreme"] < sizes["recommended"] < sizes["less"]
    assert sizes["extreme"] < original * 0.05
    assert diffs["less"] < 3 and diffs["recommended"] < 5 and diffs["extreme"] < 12
    assert diffs["less"] <= diffs["extreme"]


def test_compress_returns_unchanged_copy_when_not_smaller(tmp_path):
    src = text_pdf(tmp_path / "tiny.pdf", pages=1, toc=False, links=False)
    res = call("compress", {"file": str(src), "level": "recommended", "out_dir": str(tmp_path / "o")})
    out = only(res)
    if res["summary"]["unchanged"]:
        assert out.read_bytes() == src.read_bytes()
        assert "already" in res["summary"]["note"]
    assert out.stat().st_size <= src.stat().st_size


def test_compress_rejects_unknown_level(tmp_path):
    src = text_pdf(tmp_path / "a.pdf", pages=1)
    with pytest.raises(ToolError) as err:
        call("compress", {"file": str(src), "level": "max"})
    assert err.value.code == "bad_args"


@pytest.fixture(scope="module")
def ten_pages(tmp_path_factory) -> Path:
    return text_pdf(tmp_path_factory.mktemp("ten") / "ten.pdf", pages=10)


def test_repair_broken_xref_gives_a_clean_complete_file(ten_pages, tmp_path):
    broken = damaged_pdfs(ten_pages, tmp_path)["broken-xref"]
    res = call("repair", {"file": str(broken)})
    out = only(res)
    assert res["summary"]["pages_recovered"] == 10 and res["summary"]["pages_lost"] == 0
    with pymupdf.open(str(out)) as doc:
        assert len(doc) == 10 and not doc.is_repaired
        assert "zebra7" in doc[6].get_text()
    assert difference(render(ten_pages, 3), render(out, 3)) < 0.5


def test_repair_truncated_file_recovers_the_pages_that_survive(ten_pages, tmp_path):
    truncated = damaged_pdfs(ten_pages, tmp_path)["truncated"]
    res = call("repair", {"file": str(truncated)})
    out = only(res)
    recovered = res["summary"]["pages_recovered"]
    assert 1 <= recovered <= 10
    with pymupdf.open(str(out)) as doc:
        assert len(doc) == recovered and not doc.is_repaired
        assert "zebra1" in doc[0].get_text()
        for page in doc:
            page.get_pixmap(dpi=20)


def test_repair_cut_through_an_embedded_font_still_saves(tmp_path):
    font = Path("C:/Windows/Fonts/tahoma.ttf")
    if not font.is_file():
        pytest.skip("needs a system font to embed")
    archive = pymupdf.Archive()
    archive.add(font.read_bytes(), "tahoma.ttf")
    css = "@font-face{font-family:T;src:url(tahoma.ttf)} body{font-family:T}"
    doc = pymupdf.open()
    for number in range(3):
        doc.new_page().insert_htmlbox(pymupdf.Rect(50, 50, 545, 790), f"<h2>Chapter {number + 1}</h2><p>words</p>", css=css, archive=archive)
    whole = tmp_path / "whole.pdf"
    doc.save(str(whole))
    doc.close()
    cut = tmp_path / "cut.pdf"
    cut.write_bytes(whole.read_bytes()[: whole.stat().st_size // 2])
    out = only(call("repair", {"file": str(cut)}))
    with pymupdf.open(str(out)) as fixed:
        assert len(fixed) >= 1


def test_repair_garbage_is_a_clean_error(tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"%PDF-1.4\nthis is not really a pdf\n")
    with pytest.raises(ToolError) as err:
        call("repair", {"file": str(junk)})
    assert err.value.code == "tool_failed"


def test_pdfa_without_ghostscript_says_what_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("FREEPDF_RES", str(tmp_path / "empty"))
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "nowhere"))
    src = text_pdf(tmp_path / "a.pdf", pages=1)
    with pytest.raises(ToolError) as err:
        call("pdfa", {"file": str(src), "conformance": "2b"})
    assert err.value.code == "missing_resource"
    assert "Ghostscript" in err.value.message


@pytest.mark.skipif(find_ghostscript() is None, reason="Ghostscript is not installed")
@pytest.mark.parametrize("conformance", ["1b", "2b", "3b"])
def test_pdfa_output_is_marked_and_keeps_text(tmp_path, conformance):
    src = text_pdf(tmp_path / "a.pdf", pages=2)
    out = only(call("pdfa", {"file": str(src), "conformance": conformance}))
    with pymupdf.open(str(out)) as doc:
        assert pdfa_part(doc.get_xml_metadata()) == int(conformance[0])
        assert "OutputIntents" in doc.xref_object(doc.pdf_catalog())
        assert all(font[1] != "n/a" for font in doc[0].get_fonts())
        assert "zebra2" in doc[1].get_text()
    assert difference(render(src, 0), render(out, 0)) < 3


@pytest.mark.skipif(find_ghostscript() is None, reason="Ghostscript is not installed")
def test_pdfa_handles_arabic_and_percent_in_the_file_name(tmp_path):
    src = text_pdf(tmp_path / "التوكيد 50%d.pdf", pages=1)
    out = only(call("pdfa", {"file": str(src), "conformance": "2b"}))
    assert out.name == "التوكيد 50%d (PDFA-2b).pdf"
    with pymupdf.open(str(out)) as doc:
        assert pdfa_part(doc.get_xml_metadata()) == 2


def test_pdfa_part_reads_both_xmp_forms():
    assert pdfa_part("<x pdfaid:part='2' pdfaid:conformance='B'/>") == 2
    assert pdfa_part("<pdfaid:part>3</pdfaid:part>") == 3
    assert pdfa_part("no marker") is None


needs_ocr = pytest.mark.skipif(not HAS_TESSDATA, reason="OCR language data not installed")


@pytest.fixture(scope="module")
def scan(tmp_path_factory) -> Path:
    return scanned_pdf(tmp_path_factory.mktemp("scan") / "scan.pdf", "Hello world invoice 2024", ARABIC)


@needs_ocr
def test_ocr_round_trip_english_and_arabic_are_searchable(scan, tmp_path):
    with pymupdf.open(str(scan)) as doc:
        assert doc[0].get_text().strip() == ""
    assert call("search", {"file": str(scan), "query": "invoice"})["summary"]["hits"] == []

    res = call("ocr", {"file": str(scan), "languages": ["eng", "ara"], "out_dir": str(tmp_path)})
    out = only(res)
    assert res["summary"]["pages_read"] == 1

    def hits(query):
        return call("search", {"file": str(out), "query": query})["summary"]["hits"]

    assert hits("invoice") and hits("Hello world") and hits("Closing line")
    assert hits("مرحبا") and hits("بالعالم") and hits("مرحبا بالعالم") and hits("هذا اختبار")
    text = page_text(out, 0)
    assert "Hello world invoice 2024" in text
    assert ARABIC in text
    assert call("page_text", {"file": str(out), "page": 0})["summary"]["text"].count("2024") == 1


@needs_ocr
def test_ocr_keeps_the_page_looking_exactly_the_same(scan, tmp_path):
    out = only(call("ocr", {"file": str(scan), "out_dir": str(tmp_path)}))
    assert difference(render(scan, 0, 100), render(out, 0, 100)) == 0.0
    with pymupdf.open(str(out)) as doc:
        assert doc[0].get_image_info()
    assert out.stat().st_size < scan.stat().st_size + 150_000


@needs_ocr
def test_ocr_hits_land_on_the_words(scan, tmp_path):
    out = only(call("ocr", {"file": str(scan), "out_dir": str(tmp_path)}))
    [hit] = call("search", {"file": str(out), "query": "invoice"})["summary"]["hits"]
    x0, y0, x1, y1 = hit["rects"][0]
    pix = pymupdf.open(str(out))[0].get_pixmap(clip=pymupdf.Rect(x0, y0, x1, y1), dpi=100, alpha=False)
    dark = sum(1 for i in range(0, len(pix.samples), 3) if pix.samples[i] < 100)
    assert dark > 30, "the hit rectangle should cover printed letters"
    assert 2 < (y1 - y0) < 60 and x1 - x0 > 30


@needs_ocr
def test_ocr_skips_pages_that_already_have_text(tmp_path):
    src = text_pdf(tmp_path / "t.pdf", pages=2)
    res = call("ocr", {"file": str(src), "out_dir": str(tmp_path / "o")})
    assert res["summary"]["pages_skipped"] == 2 and res["summary"]["pages_read"] == 0


@needs_ocr
def test_ocr_reads_a_page_too_long_for_full_resolution(tmp_path):
    source = pymupdf.open()
    source.new_page(width=280, height=2800).insert_text((20, 60), "Long page sample", fontsize=8)
    picture = source[0].get_pixmap(dpi=144).tobytes("png")
    doc = pymupdf.open()
    page = doc.new_page(width=2800, height=28000)
    page.insert_image(page.rect, stream=picture)
    path = tmp_path / "long.pdf"
    doc.save(str(path))
    res = call("ocr", {"file": str(path), "out_dir": str(tmp_path / "o"), "languages": ["eng"]})
    assert "Long page sample" in page_text(only(res), 0)


@needs_ocr
def test_ocr_missing_language_data_is_a_clean_error(scan):
    with pytest.raises(ToolError) as err:
        call("ocr", {"file": str(scan), "languages": ["eng", "zzz"]})
    assert err.value.code == "missing_resource"


@needs_ocr
def test_pdf_to_word_with_ocr_keeps_the_recognised_english_and_arabic(scan, tmp_path):
    import re
    import zipfile

    import freepdf_engine.tools.from_pdf  # noqa: F401  (registers pdf_to_word)

    out = only(call("pdf_to_word", {"file": str(scan), "ocr": True, "languages": ["eng", "ara"], "out_dir": str(tmp_path)}))
    with zipfile.ZipFile(out) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    text = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", xml))
    assert "invoice" in text.lower()
    assert len(re.findall("[؀-ۿ]", text)) >= 10
    assert "<w:bidi" in xml
