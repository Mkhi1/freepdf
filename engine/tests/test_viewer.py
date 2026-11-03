import os
import time
from pathlib import Path

import pytest
from samples_pages import call, pymupdf, scanned_pdf, text_pdf

from freepdf_engine.core import ToolError, resource_dir

ARABIC = "مرحبا بالعالم هذا اختبار"
HAS_TESSDATA = all((resource_dir("tessdata") / f"{c}.traineddata").is_file() for c in ("eng", "ara"))


def summary(tool: str, **args) -> dict:
    return call(tool, args)["summary"]


def test_info_reports_pages_sizes_and_flags(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=3)
    with pymupdf.open(str(src)) as doc:
        doc.set_metadata({"title": "Study notes"})
        doc.saveIncr()
    info = summary("info", file=str(src))
    assert info["pages"] == 3 and info["sizes"] == [[595.0, 842.0]] * 3
    assert info["encrypted"] is False and info["needs_password"] is False
    assert info["scanned"] is False and info["title"] == "Study notes"
    assert info["bytes"] == src.stat().st_size


def test_info_guesses_scanned_documents(tmp_path):
    scan = scanned_pdf(tmp_path / "scan.pdf", "Some words", ARABIC)
    assert summary("info", file=str(scan))["scanned"] is True


def test_info_asks_for_a_password_instead_of_failing(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=2)
    locked = Path(call("protect", {"file": str(src), "password": "pw", "out_dir": str(tmp_path / "l")})["outputs"][0]["path"])
    asked = summary("info", file=str(locked))
    assert asked["needs_password"] is True and asked["encrypted"] is True
    opened = summary("info", file=str(locked), password="pw")
    assert opened["pages"] == 2 and opened["needs_password"] is False
    with pytest.raises(ToolError) as err:
        call("info", {"file": str(locked), "password": "bad"})
    assert err.value.code == "wrong_password"


def test_info_mixed_page_sizes(tmp_path):
    a = text_pdf(tmp_path / "a.pdf", pages=1)
    b = text_pdf(tmp_path / "b.pdf", pages=1, size=(300, 400))
    merged = Path(call("merge", {"files": [{"path": str(a)}, {"path": str(b)}]})["outputs"][0]["path"])
    assert summary("info", file=str(merged))["sizes"] == [[595.0, 842.0], [300.0, 400.0]]


def test_thumb_is_a_png_of_the_right_width_and_is_cached(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=2)
    first = summary("thumb", file=str(src), page=1, width=200)
    assert first["cached"] is False
    assert pymupdf.Pixmap(first["path"]).width == 200
    assert Path(first["path"]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    again = summary("thumb", file=str(src), page=1, width=200)
    assert again["cached"] is True and again["path"] == first["path"]
    assert summary("thumb", file=str(src), page=0, width=200)["path"] != first["path"]
    assert summary("thumb", file=str(src), page=1, width=100)["path"] != first["path"]


def test_thumb_cache_misses_when_the_file_changes(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=1)
    before = summary("thumb", file=str(src), page=0, width=120)["path"]
    stat = src.stat()
    os.utime(src, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert summary("thumb", file=str(src), page=0, width=120)["path"] != before


def test_thumb_page_out_of_range_is_a_clean_error(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=1)
    with pytest.raises(ToolError) as err:
        call("thumb", {"file": str(src), "page": 4, "width": 100})
    assert err.value.code == "bad_args"


def test_page_text_and_direction(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=2)
    result = summary("page_text", file=str(src), page=1)
    assert "zebra2" in result["text"] and result["rtl"] is False


@pytest.mark.skipif(not HAS_TESSDATA, reason="OCR language data not installed")
def test_page_text_flags_arabic_as_rtl(tmp_path):
    scan = scanned_pdf(tmp_path / "scan.pdf", "x", ARABIC)
    ocred = Path(call("ocr", {"file": str(scan), "out_dir": str(tmp_path / "o")})["outputs"][0]["path"])
    assert summary("page_text", file=str(ocred), page=0)["rtl"] is False  # mostly Latin page
    arabic_only = scanned_pdf(tmp_path / "ar.pdf", "", ARABIC + " " + ARABIC + " " + ARABIC)
    ocred2 = Path(call("ocr", {"file": str(arabic_only), "out_dir": str(tmp_path / "o2")})["outputs"][0]["path"])
    assert summary("page_text", file=str(ocred2), page=0)["rtl"] is True


def test_search_finds_every_page_with_rects_inside_the_page(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=6)
    hits = summary("search", file=str(src), query="Body text")["hits"]
    assert [h["page"] for h in hits] == list(range(6))
    for hit in hits:
        x0, y0, x1, y1 = hit["rects"][0]
        assert 0 <= x0 < x1 <= 595 and 0 <= y0 < y1 <= 842
    assert [h["page"] for h in summary("search", file=str(src), query="ZEBRA4")["hits"]] == [3]
    assert summary("search", file=str(src), query="no-such-word")["hits"] == []


def test_search_finds_arabic_stored_as_joined_letter_forms(tmp_path):
    # PDFs draw glyphs left to right, so Arabic is stored last letter first, as here.
    joined_forms = "\ufe8e\ufe92\ufea3\ufeae\ufee3"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), joined_forms, fontsize=20, fontname="ar", fontfile=r"C:\Windows\Fonts\arial.ttf")
    path = tmp_path / "joined.pdf"
    doc.save(path)
    assert "مرحبا" not in pymupdf.open(path)[0].get_text(), "the sample must keep its joined forms"
    [hit] = summary("search", file=str(path), query="مرحبا")["hits"]
    assert hit["page"] == 0 and len(hit["rects"]) == 1
    assert summary("search", file=str(path), query="كتاب")["hits"] == []


def test_search_two_matches_on_a_line_stay_two_rects(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "cat dog cat dog", fontsize=14)
    path = tmp_path / "pets.pdf"
    doc.save(str(path))
    [hit] = summary("search", file=str(path), query="cat")["hits"]
    assert len(hit["rects"]) == 2


def test_viewer_tools_are_fast_on_a_long_document(tmp_path):
    src = text_pdf(tmp_path / "long.pdf", pages=300, toc=False, links=False)
    start = time.perf_counter()
    info = summary("info", file=str(src))
    assert info["pages"] == 300 and time.perf_counter() - start < 1.0
    start = time.perf_counter()
    hits = summary("search", file=str(src), query="zebra299")["hits"]
    assert [h["page"] for h in hits] == [298]
    assert time.perf_counter() - start < 2.0
    start = time.perf_counter()
    summary("thumb", file=str(src), page=150, width=160)
    assert time.perf_counter() - start < 0.5
    start = time.perf_counter()
    summary("thumb", file=str(src), page=150, width=160)
    assert time.perf_counter() - start < 0.05
