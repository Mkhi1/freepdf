import numpy as np
import pymupdf
import pytest

from samples_markup import ARABIC, all_text, make_text_pdf, normal, raw_streams, render, run, stream_mentions

SECRET = "ACCOUNT-7731-XQZ"


def secret_pdf(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), f"Customer card number {SECRET} is private.", fontsize=12)
    page.insert_text((72, 140), "This public sentence stays untouched.", fontsize=12)
    page.insert_htmlbox(pymupdf.Rect(72, 180, 523, 230), "كلمة سرية مرحبا بالعالم نهاية",
                        css="@font-face{font-family:a;src:url(arial.ttf);}body{font-family:a;font-size:16pt;direction:rtl}",
                        archive=pymupdf.Archive(r"C:\Windows\Fonts"))
    doc.set_metadata({"title": "Secret plan", "author": "Mohammed", "subject": "private", "keywords": "k1"})
    doc.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'><rdf>Author Mohammed XMPMARK</rdf></x:xmpmeta>")
    doc.set_toc([[1, f"Section about {SECRET}", 1]])
    path = tmp_path / "secret.pdf"
    doc.save(str(path))
    doc.close()
    return path


def do_redact(path, items, **options):
    return run("redact", {"file": str(path), "items": items, **options})["outputs"][0]["path"]


def test_search_redaction_removes_text_from_every_layer(tmp_path):
    src = secret_pdf(tmp_path)
    assert stream_mentions(src, SECRET), "the sample must really contain the secret in its content stream"
    out = do_redact(src, [{"type": "search", "text": SECRET}])
    assert SECRET not in all_text(out)
    assert not stream_mentions(out, "XQZ") and not stream_mentions(out, "ACCOUNT-7731")
    assert not stream_mentions(out, "ACCOUNT")
    text = all_text(out)
    assert "This public sentence stays untouched." in text, "other text must survive"
    assert "Customer card number" in text
    with pymupdf.open(out) as doc:
        assert SECRET not in doc.get_toc()[0][1]


def test_area_redaction_blacks_out_the_area_and_removes_text(tmp_path):
    src = secret_pdf(tmp_path)
    out = do_redact(src, [{"type": "area", "page": 0, "rect": [60, 120, 400, 150]}])
    assert "public sentence" not in all_text(out)
    assert "Customer card number" in all_text(out)
    pixels = render(out, dpi=72)
    box = pixels[122:146, 75:380]
    assert box.mean() < 40, "the area is painted black"


def test_redaction_leaves_no_removed_objects_in_the_file(tmp_path):
    src = secret_pdf(tmp_path)
    out = do_redact(src, [{"type": "search", "text": "public sentence"}])
    assert stream_mentions(src, "public")
    assert not stream_mentions(out, "public") and not stream_mentions(out, "sentence")


def test_arabic_text_is_found_and_removed(tmp_path):
    src = secret_pdf(tmp_path)
    out = do_redact(src, [{"type": "search", "text": "مرحبا بالعالم"}])
    text = normal(all_text(out))
    assert "مرحبا بالعالم" not in text and "مرحبا" not in text
    assert "كلمة سرية" in text and "نهاية" in text, "words around the match stay"


def test_image_pixels_under_the_area_are_destroyed(tmp_path):
    rng = np.random.default_rng(7)
    noise = rng.integers(0, 256, (200, 200, 3), dtype=np.uint8)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(100, 100, 300, 300), pixmap=pymupdf.Pixmap(pymupdf.csRGB, 200, 200, noise.tobytes(), False))
    src = tmp_path / "img.pdf"
    doc.save(str(src))
    doc.close()
    out = do_redact(src, [{"type": "area", "page": 0, "rect": [100, 100, 200, 300]}])
    with pymupdf.open(out) as result:
        images = result[0].get_images(full=True)
        assert images, "the picture itself stays; only the covered pixels go"
        pix = pymupdf.Pixmap(result, images[0][0])
        samples = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
    assert samples.shape[:2] == (200, 200)
    covered, kept = samples[:, :95], samples[:, 105:]
    assert covered.std() < 1.0, f"covered pixels should be one flat colour, std={covered.std()}"
    assert np.array_equal(kept, noise[:, 105:]), "pixels outside the area stay identical"
    original_rows = noise[:, :100].tobytes()
    assert original_rows[:300] not in raw_streams(out), "original pixels are not hiding in another stream"
    rendered = render(out, dpi=72)[110:290, 105:195]
    assert rendered.std() < 3


def test_vector_art_under_the_area_is_removed(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(pymupdf.Rect(100, 100, 150, 150), color=(1, 0, 0), fill=(1, 0, 0))
    src = tmp_path / "vec.pdf"
    doc.save(str(src))
    out = do_redact(src, [{"type": "area", "page": 0, "rect": [90, 90, 160, 160]}], fill="#ffffff")
    with pymupdf.open(out) as result:
        reds = [d for d in result[0].get_drawings() if d.get("fill") == (1.0, 0.0, 0.0)]
    assert not reds


def test_clean_metadata_clears_info_and_xmp(tmp_path):
    src = secret_pdf(tmp_path)
    with pymupdf.open(src) as before:
        assert before.metadata["author"] == "Mohammed" and "XMPMARK" in before.get_xml_metadata()
    kept = do_redact(src, [{"type": "search", "text": SECRET}])
    with pymupdf.open(kept) as untouched:
        assert untouched.metadata["author"] == "Mohammed", "metadata stays when not asked to clear"
    out = do_redact(src, [{"type": "search", "text": SECRET}], clean_metadata=True)
    with pymupdf.open(out) as cleaned:
        meta = cleaned.metadata
        assert not any(meta.get(k) for k in ("title", "author", "subject", "keywords", "creator", "producer"))
        assert "XMPMARK" not in cleaned.get_xml_metadata()
    data = open(out, "rb").read()
    assert b"Mohammed" not in data and b"Secret plan" not in data and b"XMPMARK" not in data


def test_redaction_on_a_rotated_page_hits_the_right_area(tmp_path):
    src = make_text_pdf(tmp_path / "doc.pdf", pages=1, lines=3)
    with pymupdf.open(src) as doc:
        page = doc[0]
        native = page.search_for("Line 2 of page 1")[0]
        page.set_rotation(90)
        visual = native * page.rotation_matrix
        doc.saveIncr()
    out = do_redact(src, [{"type": "area", "page": 0, "rect": list(visual)}])
    text = all_text(out)
    assert "Line 2 of page 1" not in text
    assert "Line 1 of page 1" in text and "Line 3 of page 1" in text


def test_redact_needs_something_to_redact(tmp_path):
    from freepdf_engine.core import ToolError
    src = secret_pdf(tmp_path)
    with pytest.raises(ToolError) as caught:
        run("redact", {"file": str(src), "items": []})
    assert caught.value.code == "bad_args"
    assert ARABIC
