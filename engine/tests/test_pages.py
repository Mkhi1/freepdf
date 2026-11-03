import zipfile
from pathlib import Path

import pytest
from samples_pages import call, difference, image_heavy_pdf, page_text, pymupdf, render, text_pdf

from freepdf_engine.core import ToolError


def outputs(res) -> list[Path]:
    return [Path(o["path"]) for o in res["outputs"]]


def page_count(path: Path) -> int:
    with pymupdf.open(str(path)) as doc:
        return len(doc)


def test_merge_keeps_text_bookmarks_links_and_mixed_sizes(tmp_path):
    a = text_pdf(tmp_path / "a.pdf", pages=3)
    b = text_pdf(tmp_path / "b.pdf", pages=2, size=(842, 595))
    [out] = outputs(call("merge", {"files": [{"path": str(a)}, {"path": str(b)}]}))
    with pymupdf.open(str(out)) as doc:
        assert len(doc) == 5
        assert (doc[0].rect.width, doc[0].rect.height) == (595, 842)
        assert (doc[3].rect.width, doc[3].rect.height) == (842, 595)
        toc = doc.get_toc()
        assert [entry[1] for entry in toc] == ["Chapter 1", "Chapter 2", "Chapter 3", "Chapter 1", "Chapter 2"]
        assert [entry[2] for entry in toc] == [1, 2, 3, 4, 5]
        assert doc[3].get_links()[0]["page"] == 4
    assert "zebra3" in page_text(out, 2)
    assert difference(render(a, 1), render(out, 1)) < 1.0


def test_merge_needs_two_files(tmp_path):
    a = text_pdf(tmp_path / "a.pdf", pages=1)
    with pytest.raises(ToolError) as err:
        call("merge", {"files": [{"path": str(a)}]})
    assert err.value.code == "bad_args"


def test_split_ranges_gives_one_file_per_range(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=8)
    files = outputs(call("split", {"file": str(src), "mode": "ranges", "ranges": "1-3,5,7-8"}))
    assert [page_count(f) for f in files] == [3, 1, 2]
    assert "zebra5" in page_text(files[1], 0)


def test_split_ranges_merged_into_one(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=8)
    [out] = outputs(call("split", {"file": str(src), "mode": "ranges", "ranges": "1-2,6", "merge_output": True}))
    assert page_count(out) == 3
    assert "zebra6" in page_text(out, 2)


def test_split_every_and_extract_all(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=7)
    every = outputs(call("split", {"file": str(src), "mode": "every", "every": 3}))
    assert [page_count(f) for f in every] == [3, 3, 1]
    each = outputs(call("split", {"file": str(src), "mode": "extract_all", "out_dir": str(tmp_path / "each")}))
    assert len(each) == 7 and all(page_count(f) == 1 for f in each)


def test_split_extract_selected_pages(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=6)
    [out] = outputs(call("split", {"file": str(src), "mode": "extract", "ranges": "2,4", "merge_output": True}))
    assert page_count(out) == 2 and "zebra4" in page_text(out, 1)


def test_split_zip_contains_every_part(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=4)
    [archive] = outputs(call("split", {"file": str(src), "mode": "extract_all", "zip": True}))
    assert archive.suffix == ".zip"
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist()) == 4
    assert not list(tmp_path.glob("doc (page*"))


def test_split_size_honours_max_mb(tmp_path):
    src = image_heavy_pdf(tmp_path / "photos.pdf", pages=4)
    limit_mb = src.stat().st_size * 0.55 / 1024 / 1024
    res = call("split", {"file": str(src), "mode": "size", "max_mb": limit_mb})
    files = outputs(res)
    assert 2 <= len(files) <= 3
    assert sum(page_count(f) for f in files) == 4
    assert page_count(files[0]) >= 2
    for f in files:
        assert f.stat().st_size <= limit_mb * 1024 * 1024
    assert res["summary"]["pages_over_limit"] == 0


def test_split_size_reports_single_page_over_limit(tmp_path):
    src = image_heavy_pdf(tmp_path / "photos.pdf", pages=2)
    res = call("split", {"file": str(src), "mode": "size", "max_mb": 0.05})
    assert len(outputs(res)) == 2
    assert res["summary"]["pages_over_limit"] == 2


def test_split_rejects_page_outside_file(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=3)
    with pytest.raises(ToolError) as err:
        call("split", {"file": str(src), "mode": "ranges", "ranges": "2-9"})
    assert err.value.code == "bad_args"


def test_organize_reorders_rotates_blanks_and_pulls_from_other_file(tmp_path):
    a = text_pdf(tmp_path / "a.pdf", pages=3, toc=False)
    b = text_pdf(tmp_path / "b.pdf", pages=2, toc=False)
    plan = [
        {"source": str(a), "page": 2, "rotate": 0},
        {"source": str(a), "page": 0, "rotate": 90},
        {"blank": True},
        {"source": str(b), "page": 1, "rotate": 0},
    ]
    [out] = outputs(call("organize", {"file": str(a), "pages": plan}))
    with pymupdf.open(str(out)) as doc:
        assert len(doc) == 4
        assert "zebra3" in doc[0].get_text()
        assert doc[1].rotation == 90 and "zebra1" in doc[1].get_text()
        assert doc[2].get_text().strip() == ""
        assert (doc[2].rect.width, doc[2].rect.height) == (doc[1].rect.width, doc[1].rect.height)
        assert "zebra2" in doc[3].get_text()


def test_organize_duplicate_pages_do_not_bloat(tmp_path):
    src = text_pdf(tmp_path / "a.pdf", pages=2, toc=False)
    plan = [{"source": str(src), "page": p % 2, "rotate": 0} for p in range(10)]
    [out] = outputs(call("organize", {"file": str(src), "pages": plan}))
    assert page_count(out) == 10
    assert out.stat().st_size < src.stat().st_size * 6


def test_rotate_selected_pages_only(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=4)
    [out] = outputs(call("rotate", {"file": str(src), "angle": 90, "pages": [1, 3]}))
    with pymupdf.open(str(out)) as doc:
        assert [p.rotation for p in doc] == [0, 90, 0, 90]
        assert "zebra2" in doc[1].get_text()
    [again] = outputs(call("rotate", {"file": str(out), "angle": 270}))
    with pymupdf.open(str(again)) as doc:
        assert [p.rotation for p in doc] == [270, 0, 270, 0]


def test_rotate_rejects_odd_angle(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=1)
    with pytest.raises(ToolError):
        call("rotate", {"file": str(src), "angle": 45})


def test_crop_shrinks_page_and_keeps_the_cropped_area_pixels(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=2)
    box = [60, 80, 360, 280]
    [out] = outputs(call("crop", {"file": str(src), "box": box, "pages": [0]}))
    with pymupdf.open(str(out)) as cropped, pymupdf.open(str(src)) as original:
        assert abs(cropped[0].rect.width - 300) < 0.01 and abs(cropped[0].rect.height - 200) < 0.01
        assert (cropped[1].rect.width, cropped[1].rect.height) == (595, 842)
        want = original[0].get_pixmap(dpi=72, clip=pymupdf.Rect(*box), alpha=False)
        got = cropped[0].get_pixmap(dpi=72, alpha=False)
        assert (want.width, want.height) == (got.width, got.height)
        assert want.samples == got.samples


def test_crop_on_rotated_page_uses_what_the_user_sees(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=1)
    [rotated] = outputs(call("rotate", {"file": str(src), "angle": 90}))
    [out] = outputs(call("crop", {"file": str(rotated), "box": [0, 0, 400, 300]}))
    with pymupdf.open(str(rotated)) as original, pymupdf.open(str(out)) as cropped:
        want = original[0].get_pixmap(dpi=72, clip=pymupdf.Rect(0, 0, 400, 300), alpha=False)
        got = cropped[0].get_pixmap(dpi=72, alpha=False)
        assert want.samples == got.samples


def test_wrong_file_type_is_a_clean_error(tmp_path):
    fake = tmp_path / "x.pdf"
    fake.write_text("not a pdf at all")
    with pytest.raises(ToolError) as err:
        call("rotate", {"file": str(fake), "angle": 90})
    assert err.value.code == "not_a_pdf"
