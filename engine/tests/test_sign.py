import numpy as np
import pymupdf
import pytest
from fontTools.ttLib import TTFont
from PIL import Image

from samples_markup import ARABIC, has_joined_forms, make_text_pdf, normal, render, render_rgb, run


def make_signature(tmp_path, **options):
    reply = run("make_signature", {"out_dir": str(tmp_path), **options})
    return reply["outputs"][0]["path"], reply["summary"]


def test_typed_signature_is_a_transparent_png_in_the_chosen_colour(tmp_path):
    path, summary = make_signature(tmp_path, text="Mohammed Khalid", font="script", color="#102a73")
    img = Image.open(path)
    assert img.mode == "RGBA"
    alpha = np.asarray(img)[:, :, 3]
    assert alpha[0, 0] == 0 and alpha[-1, -1] == 0, "corners must be transparent"
    assert 0.03 < (alpha > 0).mean() < 0.5, "ink should be a part of the picture, not all of it"
    solid = np.asarray(img)[alpha > 250][:, :3]
    assert np.abs(solid.mean(axis=0) - (0x10, 0x2a, 0x73)).max() < 12
    assert img.width > img.height * 3, img.size
    assert summary["font"].lower() == "segoesc.ttf"


def test_drawn_signature_is_saved_as_signed_with_ink_in_place(tmp_path):
    src = make_text_pdf(tmp_path / "doc.pdf", pages=1, lines=0)
    stroke = [[100, 500], [160, 470], [220, 520], [300, 480]]
    out = run("sign", {"file": str(src), "items": [
        {"type": "ink", "page": 0, "points": stroke, "color": "#102a73", "width": 3},
    ]})["outputs"][0]["path"]
    assert "(signed)" in out
    pixels = render(out)
    assert (pixels[460:530, 95:305] < 200).any(), "the stroke should be drawn where it was placed"
    assert (pixels[600:, :] > 250).all(), "nothing should be drawn elsewhere"


def test_signature_styles_look_different(tmp_path):
    first, _ = make_signature(tmp_path, text="Sara Ali", font="script")
    second, info = make_signature(tmp_path, text="Sara Ali", font="brush")
    a, b = Image.open(first), Image.open(second)
    assert info["font"].lower() in ("brushsci.ttf", "segoescb.ttf")  # Brush Script only ships with Office
    same = a.size == b.size and np.array_equal(np.asarray(a), np.asarray(b))
    assert not same


def test_arabic_signature_uses_an_arabic_font_and_joins(tmp_path):
    path, summary = make_signature(tmp_path, text=ARABIC, font="script", color="#000000", size=48)
    cmap = TTFont(rf"C:\Windows\Fonts\{summary['font']}", fontNumber=0).getBestCmap()
    assert all(ord(ch) in cmap for ch in ARABIC if ch != " "), "font must contain every Arabic letter"
    img = Image.open(path)
    alpha = np.asarray(img)[:, :, 3]
    assert (alpha > 0).any()
    isolated = pymupdf.Font(fontfile=rf"C:\Windows\Fonts\{summary['font']}").text_length(ARABIC, 48)
    assert img.width / 4 < isolated * 1.05, "joined letters should not be wider than separate letters"


def test_signature_with_transparency_keeps_it_on_the_page(tmp_path):
    src = make_text_pdf(tmp_path / "doc.pdf", pages=1, lines=0)
    with pymupdf.open(src) as doc:
        doc[0].draw_rect(pymupdf.Rect(0, 600, 595, 842), color=None, fill=(1, 1, 0.5))
        doc.saveIncr()
    sig = tmp_path / "sig.png"
    img = Image.new("RGBA", (200, 100), (200, 0, 0, 255))
    for x in range(100, 200):
        for y in range(100):
            img.putpixel((x, y), (0, 0, 0, 0))
    img.save(sig)
    out = run("sign", {"file": str(src), "items": [{"type": "signature", "page": 0, "rect": [100, 650, 300, 750],
                                                    "image_path": str(sig)}]})["outputs"][0]["path"]
    rgb = render_rgb(out).astype(int)
    assert tuple(rgb[700, 150]) == (200, 0, 0)               # opaque half
    assert np.abs(rgb[700, 250] - (255, 255, 128)).max() <= 2  # transparent half shows the yellow behind
    with pymupdf.open(out) as doc:
        assert len(doc[0].get_images()) == 1


def test_sign_places_typed_signature_and_arabic_text_field(tmp_path):
    src = make_text_pdf(tmp_path / "doc.pdf", pages=2, lines=1)
    sig, _ = make_signature(tmp_path, text="Dana", font="ink", color="#000000")
    out = run("sign", {"file": str(src), "items": [
        {"type": "signature", "page": 1, "rect": [72, 300, 272, 360], "image_path": sig},
        {"type": "text_field", "page": 1, "x": 72, "y": 400, "text": ARABIC, "size": 20},
        {"type": "text_field", "page": 1, "x": 72, "y": 440, "text": "Date: 2026-10-30", "size": 12},
    ]})["outputs"][0]["path"]
    with pymupdf.open(out) as doc:
        raw = doc[1].get_text()
    assert ARABIC in normal(raw) and has_joined_forms(raw)
    assert "Date: 2026-10-30" in raw
    ink = render(out, page_number=1, dpi=144, clip=pymupdf.Rect(72, 300, 272, 360))
    assert (ink < 128).sum() > 400, "the signature should paint dark pixels inside its rectangle"


def test_sign_errors_are_clear(tmp_path):
    from freepdf_engine.core import ToolError
    src = make_text_pdf(tmp_path / "doc.pdf", pages=1)
    with pytest.raises(ToolError) as caught:
        run("sign", {"file": str(src), "items": [{"type": "signature", "page": 3, "rect": [0, 0, 1, 1], "image_path": "x"}]})
    assert caught.value.code == "bad_args"
    with pytest.raises(ToolError) as empty:
        run("make_signature", {"text": "  ", "out_dir": str(tmp_path)})
    assert empty.value.code == "bad_args"
