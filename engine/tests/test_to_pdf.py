import http.server
import threading
import time
from functools import partial
from pathlib import Path

import psutil
import pymupdf
import pytest
from PIL import Image

import samples_convert as S
from freepdf_engine.core import Job, ToolError
from freepdf_engine.office import run_office
from freepdf_engine.tools.to_pdf import _office_installed as office_installed
from freepdf_engine.registry import TOOLS
import freepdf_engine.tools.to_pdf  # noqa: F401  (registers tools)


def run(tool: str, **args) -> dict:
    job = Job("t", lambda message: None, threading.Event())
    return TOOLS[tool](job, args)


def first_output(outcome: dict) -> Path:
    return Path(outcome["outputs"][0]["path"])


def page_count(path: Path) -> int:
    with pymupdf.open(str(path)) as doc:
        return doc.page_count


def count_office(name: str) -> int:
    return sum(1 for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == name)


# ---------- Office conversions ----------

def test_word_english_text_recall(tmp_path):
    src = S.make_docx(tmp_path / "english.docx", "english")
    out = first_output(run("word_to_pdf", files=[str(src)]))
    recall = S.text_recall("\n".join(S.ENGLISH_LINES * 3) + " Study Notes", S.pdf_text(out))
    assert recall >= 0.99, recall


def test_word_arabic_text_recall(tmp_path):
    src = S.make_docx(tmp_path / "arabic.docx", "arabic")
    out = first_output(run("word_to_pdf", files=[str(src)]))
    recall = S.text_recall("\n".join(S.ARABIC_LINES * 3), S.pdf_text(out))
    assert recall >= 0.95, recall


def test_word_table_and_columns_and_images(tmp_path):
    table = first_output(run("word_to_pdf", files=[str(S.make_docx(tmp_path / "table.docx", "table"))]))
    text = S.pdf_text(table)
    assert all(cell in text for row in S.TABLE_ROWS for cell in row)
    pics = first_output(run("word_to_pdf", files=[str(S.make_docx(tmp_path / "images.docx", "images"))]))
    assert len(S.image_bytes_of(pics)) >= 1
    cols = first_output(run("word_to_pdf", files=[str(S.make_docx(tmp_path / "cols.docx", "columns"))]))
    with pymupdf.open(str(cols)) as doc:
        xs = {round(b[0] / 50) for b in doc[0].get_text("blocks") if b[4].strip()}
    assert len(xs) >= 2  # text blocks start at two different horizontal positions


def test_excel_and_powerpoint(tmp_path):
    xl = first_output(run("excel_to_pdf", files=[str(S.make_xlsx(tmp_path / "grades.xlsx"))]))
    text = S.pdf_text(xl)
    assert "Amal" in text and "91" in text and "Student" in text
    pp = first_output(run("ppt_to_pdf", files=[str(S.make_pptx(tmp_path / "deck.pptx"))]))
    assert "Quarterly Review" in S.pdf_text(pp)
    with pymupdf.open(str(pp)) as doc:
        assert abs(doc[0].rect.width / doc[0].rect.height - 4 / 3) < 0.01


def test_merge_output_and_separate(tmp_path):
    a = S.make_docx(tmp_path / "a.docx", "english")
    b = S.make_xlsx(tmp_path / "b.xlsx")
    outcome = run("word_to_pdf", files=[str(a)], merge_output=True)
    assert len(outcome["outputs"]) == 1
    two = run("word_to_pdf", files=[str(a), str(a)], merge_output=True)
    assert len(two["outputs"]) == 1 and page_count(first_output(two)) == 2 * page_count(first_output(outcome))
    separate = run("word_to_pdf", files=[str(a), str(a)])
    assert len(separate["outputs"]) == 2
    with pytest.raises(ToolError) as err:
        run("word_to_pdf", files=[str(b)])
    assert err.value.code == "bad_args"


@pytest.mark.skipif(not office_installed("word"), reason="needs Microsoft Word")
def test_office_hang_is_killed_with_clear_error():
    before = count_office("winword.exe")
    start = time.time()
    with pytest.raises(ToolError) as err:
        run_office("word", lambda app: time.sleep(60), timeout=3)
    assert err.value.code == "office_failed" and "did not finish" in err.value.message
    assert time.time() - start < 20
    time.sleep(1)
    assert count_office("winword.exe") <= before


# ---------- images to PDF ----------

def test_jpeg_is_never_recompressed(tmp_path):
    jpg = S.make_jpeg(tmp_path / "photo.jpg")
    for page_size in ("fit", "a4"):
        out = first_output(run("images_to_pdf", files=[str(jpg)], page_size=page_size, margin="small"))
        assert S.image_bytes_of(out)[0] == jpg.read_bytes()


def red_corner(path: Path) -> str:
    with pymupdf.open(str(path)) as doc:
        pix = doc[0].get_pixmap(dpi=36)
    w, h = pix.width, pix.height

    def is_red(x, y):
        r, g, b = pix.pixel(x, y)[:3]
        return r > 200 and g < 80 and b < 80
    spots = {"tl": (3, 3), "tr": (w - 4, 3), "bl": (3, h - 4), "br": (w - 4, h - 4)}
    hits = [name for name, (x, y) in spots.items() if is_red(x, y)]
    return hits[0] if hits else "none"


@pytest.mark.parametrize("orientation,corner,swapped", [(1, "tl", False), (3, "br", False), (6, "tr", True), (8, "bl", True)])
def test_exif_rotation_respected(tmp_path, orientation, corner, swapped):
    jpg = S.make_jpeg(tmp_path / f"o{orientation}.jpg", (640, 400), orientation)
    out = first_output(run("images_to_pdf", files=[str(jpg)], page_size="fit"))
    with pymupdf.open(str(out)) as doc:
        rect = doc[0].rect
    assert (rect.height > rect.width) == swapped
    assert red_corner(out) == corner
    assert S.image_bytes_of(out)[0] == jpg.read_bytes()


def test_page_sizes_orientation_margins(tmp_path):
    jpg = S.make_jpeg(tmp_path / "p.jpg")
    expect = {("a4", "portrait"): (595.3, 841.9), ("a4", "landscape"): (841.9, 595.3),
              ("letter", "portrait"): (612, 792), ("letter", "landscape"): (792, 612)}
    for (size, orient), (w, h) in expect.items():
        out = first_output(run("images_to_pdf", files=[str(jpg)], page_size=size, orientation=orient, margin="big"))
        with pymupdf.open(str(out)) as doc:
            page = doc[0]
            assert abs(page.rect.width - w) < 1 and abs(page.rect.height - h) < 1
            box = page.get_image_rects(page.get_images()[0][0])[0]
            assert box.x0 >= 49.9 and box.y0 >= 49.9 and box.x1 <= w - 49.9 and box.y1 <= h - 49.9


def test_every_format_and_separate_outputs(tmp_path):
    base = S.photo_png(tmp_path / "src.png", (200, 120))
    files = [S.make_jpeg(tmp_path / "a.jpg"), base]
    img = Image.open(base)
    img.save(tmp_path / "c.webp")
    img.save(tmp_path / "d.bmp")
    img.save(tmp_path / "e.tiff")
    img.convert("P").save(tmp_path / "f.gif")
    rgba = img.convert("RGBA")
    rgba.putalpha(128)
    rgba.save(tmp_path / "g.png")
    files += [tmp_path / n for n in ("c.webp", "d.bmp", "e.tiff", "f.gif", "g.png")]
    merged = run("images_to_pdf", files=[str(f) for f in files], merge_output=True)
    assert page_count(first_output(merged)) == len(files)
    separate = run("images_to_pdf", files=[str(f) for f in files], merge_output=False)
    assert len(separate["outputs"]) == len(files)
    with pytest.raises(ToolError):
        run("images_to_pdf", files=[str(tmp_path / "x.txt")])


def test_png_pixels_are_lossless(tmp_path):
    png = S.photo_png(tmp_path / "lossless.png", (300, 200))
    out = first_output(run("images_to_pdf", files=[str(png)], page_size="fit"))
    with pymupdf.open(str(out)) as doc:
        xref = doc[0].get_images()[0][0]
        pix = pymupdf.Pixmap(doc, xref)
    original = Image.open(png).convert("RGB")
    assert pix.width == 300 and pix.samples == original.tobytes()


# ---------- HTML to PDF ----------

HTML = "<html><body style='font-family:Arial'><h1>Hello Report</h1><p>Chromium quality text.</p>{}</body></html>"


@pytest.fixture(scope="module")
def html_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("html") / "page.html"
    path.write_text(HTML.format("<p style='margin-top:3000px'>Bottom marker</p>"), encoding="utf-8")
    return path


def test_html_local_file_and_page_options(html_file):
    out = first_output(run("html_to_pdf", source=str(html_file), page_size="letter", orientation="landscape"))
    with pymupdf.open(str(out)) as doc:
        assert abs(doc[0].rect.width - 792) < 1 and abs(doc[0].rect.height - 612) < 1
        assert doc.page_count >= 2
        assert "Hello Report" in doc[0].get_text()


def test_html_one_long_page_and_margin(html_file):
    out = first_output(run("html_to_pdf", source=html_file.as_uri(), one_long_page=True, margin="none"))
    with pymupdf.open(str(out)) as doc:
        assert doc.page_count == 1 and doc[0].rect.height > 2000
        assert "Bottom marker" in doc[0].get_text()
    big = first_output(run("html_to_pdf", source=str(html_file), margin="big"))
    none = first_output(run("html_to_pdf", source=str(html_file), margin="none"))
    with pymupdf.open(str(big)) as a, pymupdf.open(str(none)) as b:
        assert a[0].get_text("blocks")[0][0] > b[0].get_text("blocks")[0][0] + 40


def test_html_from_http_url(tmp_path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text(HTML.format(""), encoding="utf-8")
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path / "site"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        out = first_output(run("html_to_pdf", source=f"http://127.0.0.1:{server.server_port}/index.html", out_dir=str(tmp_path)))
    finally:
        server.shutdown()
    assert "Chromium quality text" in S.pdf_text(out)


@pytest.mark.parametrize("source", ["ftp://example.com/a.html", "javascript:alert(1)", "data:text/html,hi", "chrome://settings", "C:\\no\\such\\file.html"])
def test_html_rejects_bad_sources(source):
    with pytest.raises(ToolError):
        run("html_to_pdf", source=source)


def test_html_leaves_no_edge_behind(html_file):
    before = count_office("msedge.exe")
    run("html_to_pdf", source=str(html_file))
    time.sleep(1)
    assert count_office("msedge.exe") <= before


# ---------- scanner (hardware not available in tests) ----------

def test_scanner_listing_and_clear_error_without_device():
    devices = run("list_scanners")["summary"]["devices"]
    assert isinstance(devices, list)
    if not devices:
        with pytest.raises(ToolError) as err:
            run("scan_to_pdf", dpi=150)
        assert "No scanner" in err.value.message
