import numpy as np
import pymupdf
import pytest
from PIL import Image

from samples_markup import (ARABIC, has_joined_forms, ink_box, make_arabic_pdf, make_text_pdf, normal,
                            principal_angle, render, render_rgb, run)


@pytest.fixture()
def blank(tmp_path):
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page(width=595, height=842)
    path = tmp_path / "blank.pdf"
    doc.save(str(path))
    return path


def watermark(path, **options):
    return run("watermark", {"file": str(path), **options})["outputs"][0]["path"]


def test_watermark_opacity_really_applies(blank):
    darkest = {}
    for opacity in (1.0, 0.3):
        out = watermark(blank, text="DRAFT", size=80, color="#000000", opacity=opacity, position="center")
        darkest[opacity] = int(render(out).min())
    assert darkest[1.0] < 20
    assert 160 <= darkest[0.3] <= 195, darkest  # 255 * (1 - 0.3) = 178


def test_watermark_all_nine_positions(blank):
    expected = {"top-left": (0, 0), "top-center": (1, 0), "top-right": (2, 0),
                "middle-left": (0, 1), "center": (1, 1), "middle-right": (2, 1),
                "bottom-left": (0, 2), "bottom-center": (1, 2), "bottom-right": (2, 2)}
    for name, (col, row) in expected.items():
        out = watermark(blank, text="WM", size=40, color="#000000", opacity=1, position=name)
        left, top, right, bottom = ink_box(render(out))
        cx, cy = (left + right) / 2, (top + bottom) / 2
        assert col * 595 / 3 <= cx <= (col + 1) * 595 / 3, (name, cx)
        assert row * 842 / 3 <= cy <= (row + 1) * 842 / 3, (name, cy)


def test_watermark_rotation_turns_the_text_45_degrees(blank):
    straight = render(watermark(blank, text="CONFIDENTIAL", size=60, color="#000000", opacity=1))
    turned = render(watermark(blank, text="CONFIDENTIAL", size=60, color="#000000", opacity=1, rotation=45))
    assert min(principal_angle(straight), 180 - principal_angle(straight)) < 3
    assert 40 <= principal_angle(turned) <= 50, principal_angle(turned)


def test_watermark_mosaic_repeats_across_the_page(blank):
    out = watermark(blank, text="DRAFT", size=30, mosaic=True, opacity=0.5, rotation=30)
    with pymupdf.open(out) as doc:
        count = doc[0].get_text().upper().count("DRAFT")
    assert count >= 8, count


def test_watermark_page_range(blank):
    out = watermark(blank, text="ONLYTWO", from_page=2, to_page=2)
    with pymupdf.open(out) as doc:
        found = [("ONLYTWO" in page.get_text()) for page in doc]
    assert found == [False, True, False]


def test_watermark_under_layer_sits_behind_page_content(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(page.rect, color=None, fill=(1, 1, 0.6))
    path = tmp_path / "yellow.pdf"
    doc.save(str(path))
    under = watermark(path, text="BEHIND", size=100, color="#000000", opacity=1, layer="under")
    over = watermark(path, text="BEHIND", size=100, color="#000000", opacity=1, layer="over")
    assert int(render(under).min()) > 200, "the page fill should hide an under-layer watermark"
    assert int(render(over).min()) < 30
    with pymupdf.open(under) as result:
        streams = [result.xref_stream(x).decode("latin-1") for x in result[0].get_contents()]
    assert streams.index(next(s for s in streams if "BT" in s or "Tj" in s or "TJ" in s)) < \
        streams.index(next(s for s in streams if " re" in s and "f" in s))


def test_watermark_image_keeps_alpha_and_applies_opacity(blank, tmp_path):
    png = tmp_path / "mark.png"
    img = Image.new("RGBA", (200, 100), (255, 0, 0, 255))
    for x in range(100, 200):
        for y in range(100):
            img.putpixel((x, y), (255, 0, 0, 0))  # right half fully transparent
    img.save(png)
    out = watermark(blank, kind="image", image_path=str(png), opacity=0.5, position="center", scale=0.5)
    rgb = render_rgb(out).astype(int)
    left = rgb[421, 595 // 2 - 60]
    right = rgb[421, 595 // 2 + 60]
    assert abs(left[0] - 255) <= 3 and abs(left[1] - 128) <= 6, left   # half-red over white
    assert tuple(right) == (255, 255, 255), right                       # transparency kept


def test_watermark_image_rotation_and_mosaic(blank, tmp_path):
    png = tmp_path / "logo.png"
    Image.new("RGBA", (120, 40), (0, 0, 255, 255)).save(png)
    turned = render(watermark(blank, kind="image", image_path=str(png), opacity=1, rotation=45))
    assert 40 <= principal_angle(turned) <= 50
    tiled = watermark(blank, kind="image", image_path=str(png), mosaic=True, scale=0.15, opacity=1)
    with pymupdf.open(tiled) as doc:
        assert len(doc[0].get_images()) >= 6


def test_watermark_arabic_joins_and_reads_back(blank):
    out = watermark(blank, text=ARABIC, size=50, color="#000000", opacity=1, position="center")
    with pymupdf.open(out) as doc:
        raw = doc[0].get_text()
    assert ARABIC in normal(raw)
    assert has_joined_forms(raw)
    assert ink_box(render(out)) is not None


def test_watermark_arabic_rotated_is_turned(blank):
    out = watermark(blank, text=ARABIC, size=60, color="#000000", opacity=1, rotation=45)
    assert 40 <= principal_angle(render(out)) <= 50


def test_watermark_font_styles(blank):
    out = watermark(blank, text="Styled", bold=True, italic=True, underline=True, size=40)
    with pymupdf.open(out) as doc:
        fonts = " ".join(f[3] for f in doc[0].get_fonts())
        lines = [d for d in doc[0].get_drawings() if d["type"] == "s"]
    assert "Bold" in fonts and ("Italic" in fonts or "Oblique" in fonts), fonts
    assert lines, "underline should be drawn"


def numbers(path, **options):
    return run("page_numbers", {"file": str(path), **options})["outputs"][0]["path"]


def number_box(path, page=0):
    with pymupdf.open(path) as doc:
        words = doc[page].get_text("words")
        assert words, "no number was added"
        x0, y0, x1, y1 = words[0][:4]
        return x0, y0, x1, y1, doc[page].rect


def test_page_numbers_all_six_positions(blank):
    for position in ("top-left", "top-center", "top-right", "bottom-left", "bottom-center", "bottom-right"):
        x0, y0, x1, y1, rect = number_box(numbers(blank, position=position, margin="recommended"))
        horizontal = position.split("-")[1]
        if horizontal == "left":
            assert abs(x0 - 36) < 1.5
        elif horizontal == "right":
            assert abs(rect.width - 36 - x1) < 1.5
        else:
            assert abs((x0 + x1) / 2 - rect.width / 2) < 1.5
        if position.startswith("top"):
            assert 30 < y0 < 48
        else:
            assert rect.height - 48 < y1 < rect.height - 30


def test_page_numbers_margins_differ(blank):
    gaps = {}
    for margin in ("small", "recommended", "big"):
        _, _, _, y1, rect = number_box(numbers(blank, position="bottom-center", margin=margin))
        gaps[margin] = rect.height - y1
    assert gaps["small"] < gaps["recommended"] < gaps["big"], gaps


def test_page_numbers_first_number_range_and_total(blank):
    out = numbers(blank, first_number=5, from_page=2, to_page=3, format="Page {n} of {total}")
    with pymupdf.open(out) as doc:
        texts = [page.get_text().strip() for page in doc]
    assert texts == ["", "Page 5 of 6", "Page 6 of 6"]


def test_page_numbers_facing_pages_are_mirrored(blank):
    out = numbers(blank, position="bottom-right", facing=True)
    right = number_box(out, 0)
    left = number_box(out, 1)
    third = number_box(out, 2)
    assert right[0] > 400 and left[0] < 100 and third[0] > 400, (right[0], left[0], third[0])


def test_page_numbers_arabic_text_and_digits(blank):
    out = numbers(blank, format="صفحة {n}", numerals="arabic")
    with pymupdf.open(out) as doc:
        text = normal(doc[1].get_text())
    # the renderer may hand back the Persian form of the digit, which looks the same for 2
    assert text.strip() in ("صفحة ٢", "صفحة ۲"), text
    assert has_joined_forms(doc_page_text(out, 1))


def doc_page_text(path, index):
    with pymupdf.open(path) as doc:
        return doc[index].get_text()


def edit(path, items):
    return run("edit", {"file": str(path), "items": items})["outputs"][0]["path"]


def test_edit_text_shapes_ink_image_and_whiteout(tmp_path):
    src = make_text_pdf(tmp_path / "doc.pdf", pages=1)
    png = tmp_path / "pic.png"
    Image.new("RGBA", (60, 60), (0, 160, 0, 255)).save(png)
    out = edit(src, [
        {"type": "whiteout", "page": 0, "rect": [60, 110, 540, 135], "color": "#ffffff"},
        {"type": "text", "page": 0, "x": 72, "y": 300, "text": "Added with edit é", "size": 18, "color": "#cc0000"},
        {"type": "shape", "page": 0, "kind": "rect", "rect": [72, 400, 172, 450], "stroke": "#0000ff", "fill": "#ffff00"},
        {"type": "shape", "page": 0, "kind": "ellipse", "rect": [200, 400, 300, 450], "stroke": "#000000", "width": 3},
        {"type": "shape", "page": 0, "kind": "arrow", "rect": [350, 400, 450, 450], "stroke": "#000000", "width": 2},
        {"type": "ink", "page": 0, "points": [[72, 500], [100, 520], [140, 490], [180, 530]], "color": "#00aa00", "width": 3},
        {"type": "image", "page": 0, "rect": [400, 500, 460, 560], "path": str(png), "rotate": 0},
    ])
    with pymupdf.open(out) as doc:
        page = doc[0]
        assert "Added with edit é" in page.get_text()
        assert len(page.get_images()) == 1
    rgb = render_rgb(out)
    assert tuple(rgb[425, 120]) == (255, 255, 0)             # filled rect
    assert tuple(rgb[530, 430]) == (0, 160, 0)               # image pixel
    assert rgb[122, 100:400].min() > 250                     # whiteout hides the line below it
    assert (rgb[490:535, 72:182, 1] > rgb[490:535, 72:182, 0] + 100).sum() > 100  # green ink stroke


def test_edit_arabic_text_joins_and_reads_back(tmp_path):
    src = make_text_pdf(tmp_path / "doc.pdf", pages=1, lines=1)
    out = edit(src, [{"type": "text", "page": 0, "x": 100, "y": 300, "text": ARABIC, "size": 24}])
    with pymupdf.open(out) as doc:
        raw = doc[0].get_text()
        fonts = [f[3] for f in doc[0].get_fonts()]
    assert ARABIC in normal(raw)
    assert has_joined_forms(raw)
    assert any("Arial" in f for f in fonts), fonts
    box = ink_box(render(out, dpi=144, clip=pymupdf.Rect(90, 290, 500, 340)))
    assert box is not None
    # joined glyphs: shaped width is clearly narrower than the same letters set apart
    shaped = (box[2] - box[0]) / 2
    isolated = pymupdf.Font(fontfile=r"C:\Windows\Fonts\arial.ttf").text_length(ARABIC, 24)
    assert shaped < isolated, (shaped, isolated)


def test_edit_text_on_rotated_page_lands_where_asked(tmp_path):
    src = make_text_pdf(tmp_path / "doc.pdf", pages=1, lines=0)
    with pymupdf.open(src) as doc:
        doc[0].set_rotation(90)
        doc.saveIncr()
    out = edit(src, [{"type": "text", "page": 0, "x": 100, "y": 200, "text": "UPRIGHT", "size": 20}])
    with pymupdf.open(out) as doc:
        page = doc[0]
        found = page.search_for("UPRIGHT")[0] * page.rotation_matrix
    assert abs(found.x0 - 100) < 3 and 195 < found.y0 < 205 and found.width > found.height * 2, found


def annotate(path, items):
    return run("annotate", {"file": str(path), "items": items})["outputs"][0]["path"]


def test_annotations_are_real_with_appearance_streams(tmp_path):
    src = make_text_pdf(tmp_path / "doc.pdf", pages=1)
    with pymupdf.open(src) as doc:
        target = doc[0].search_for("Chapter 1 heading")[0]
    out = annotate(src, [
        {"type": "highlight", "page": 0, "rects": [list(target)], "color": "#ffee00"},
        {"type": "underline", "page": 0, "text": "quick brown fox"},
        {"type": "strikeout", "page": 0, "text": "lazy dog"},
        {"type": "note", "page": 0, "x": 20, "y": 20, "text": "Remember this - مرحبا"},
        {"type": "ink", "page": 0, "points": [[100, 600], [150, 650], [200, 600]], "color": "#ff0000", "width": 3},
        {"type": "freetext", "page": 0, "rect": [72, 700, 300, 740], "text": "Free text box", "size": 14},
    ])
    with pymupdf.open(out) as doc:
        page = doc[0]
        names = [a.type[1] for a in page.annots()]
        assert names.count("Underline") >= 1 and names.count("StrikeOut") >= 1
        assert {"Highlight", "Text", "Ink", "FreeText"} <= set(names), names
        for annot in page.annots():
            assert doc.xref_get_key(annot.xref, "AP")[0] != "null", annot.type
        note = next(a for a in page.annots() if a.type[1] == "Text")
        assert "مرحبا" in note.info["content"]
    plain = render_rgb(src).astype(int)
    shown = render_rgb(out).astype(int)
    changed = (np.abs(plain - shown).sum(axis=2) > 60).sum()
    assert changed > 800, changed  # annotations paint real pixels in a normal renderer


def test_edit_rejects_a_bad_page_with_a_clear_message(tmp_path):
    from freepdf_engine.core import ToolError
    src = make_text_pdf(tmp_path / "doc.pdf", pages=1)
    with pytest.raises(ToolError) as caught:
        edit(src, [{"type": "text", "page": 5, "x": 1, "y": 1, "text": "x"}])
    assert caught.value.code == "bad_args"


def test_arabic_sample_is_shaped(tmp_path):
    path = make_arabic_pdf(tmp_path / "ar.pdf")
    with pymupdf.open(path) as doc:
        assert has_joined_forms(doc[0].get_text())


def test_page_numbers_with_arabic_digits_keep_english_words_in_order(blank):
    out = run("page_numbers", {"file": str(blank), "format": "Page {n}", "numerals": "arabic"})["outputs"][0]["path"]
    with pymupdf.open(out) as doc:
        text = doc[0].get_text().strip()
    assert text.startswith("Page") and text[-1] in "١۱"
