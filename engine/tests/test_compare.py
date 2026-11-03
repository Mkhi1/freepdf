import numpy as np
import pymupdf
import pytest
from PIL import Image

from samples_markup import make_text_pdf, run


def compare(a, b, **options):
    return run("compare", {"file_a": str(a), "file_b": str(b), **options})


def edited_copy(src, dst, replacements=(), extra_pages=(), drop_last=False, rects=()):
    with pymupdf.open(src) as doc:
        for page_no, old, new in replacements:
            page = doc[page_no]
            for hit in page.search_for(old):
                page.add_redact_annot(hit, fill=(1, 1, 1))
                page.apply_redactions()
                page.insert_text((hit.x0, hit.y1 - 2.5), new, fontsize=11)
        for page_no, rect in rects:
            doc[page_no].draw_rect(pymupdf.Rect(rect), color=None, fill=(0, 0, 0))
        for position in extra_pages:
            doc.new_page(position, width=595, height=842).insert_text((72, 100), "Inserted page about rivers", fontsize=14)
        if drop_last:
            doc.delete_page(doc.page_count - 1)
        doc.save(str(dst))
    return dst


@pytest.fixture()
def pair(tmp_path):
    a = make_text_pdf(tmp_path / "old.pdf", pages=3)
    b = edited_copy(a, tmp_path / "new.pdf", replacements=[(1, "quick", "slow")])
    return a, b


def test_text_mode_finds_exactly_the_changed_words_with_rects(pair):
    a, b = pair
    reply = compare(a, b, mode="text")
    pages = reply["summary"]["pages"]
    assert [p["changed"] for p in pages] == [False, True, False]
    page = pages[1]
    removed = " ".join(i["text"] for i in page["removed"])
    added = " ".join(i["text"] for i in page["added"])
    assert "quick" in removed and "slow" in added
    assert "brown" not in removed and "brown" not in added
    with pymupdf.open(a) as da, pymupdf.open(b) as db:
        true_removed = da[1].search_for("quick")[0]
        true_added = db[1].search_for("slow")[0]
    found_removed = pymupdf.Rect(page["removed"][0]["rect"])
    found_added = pymupdf.Rect(page["added"][0]["rect"])
    assert (found_removed & true_removed).get_area() / true_removed.get_area() > 0.9
    assert (found_added & true_added).get_area() / true_added.get_area() > 0.9
    assert len(page["removed"]) == 6 and len(page["added"]) == 6  # one changed word on each of 6 lines


def test_text_mode_counts_are_exact_for_a_single_change(tmp_path):
    a = make_text_pdf(tmp_path / "old.pdf", pages=1, lines=1)
    b = edited_copy(a, tmp_path / "new.pdf", replacements=[(0, "lazy", "sleepy")])
    page = compare(a, b)["summary"]["pages"][0]
    assert [i["text"] for i in page["removed"]] == ["lazy"]
    assert [i["text"] for i in page["added"]] == ["sleepy"]


def test_inserted_and_missing_pages_do_not_shift_the_rest(tmp_path):
    a = make_text_pdf(tmp_path / "old.pdf", pages=3)
    b = edited_copy(a, tmp_path / "ins.pdf", extra_pages=[1])
    reply = compare(a, b)["summary"]
    assert (reply["pages_a"], reply["pages_b"]) == (3, 4)
    changed = [p for p in reply["pages"] if p["changed"]]
    assert len(changed) == 1
    assert changed[0]["page_a"] is None and changed[0]["page_b"] == 1
    assert "rivers" in " ".join(i["text"] for i in changed[0]["added"])
    shorter = edited_copy(a, tmp_path / "short.pdf", drop_last=True)
    dropped = compare(a, shorter)["summary"]
    gone = [p for p in dropped["pages"] if p["changed"]]
    assert len(gone) == 1 and gone[0]["page_b"] is None and gone[0]["page_a"] == 2
    assert gone[0]["removed"] and not gone[0]["added"]


def test_identical_files_report_no_changes(tmp_path):
    a = make_text_pdf(tmp_path / "old.pdf", pages=2)
    assert compare(a, a)["summary"]["changed_pages"] == 0


def test_arabic_changes_are_found(tmp_path):
    def arabic_pdf(path, sentence):
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        page.insert_htmlbox(pymupdf.Rect(72, 80, 523, 200), sentence, archive=pymupdf.Archive(r"C:\Windows\Fonts"),
                            css="@font-face{font-family:a;src:url(arial.ttf);}body{font-family:a;font-size:16pt;direction:rtl}")
        doc.save(str(path))
        return path
    a = arabic_pdf(tmp_path / "a.pdf", "الكتاب الجديد على الطاولة")
    b = arabic_pdf(tmp_path / "b.pdf", "الكتاب القديم على الطاولة")
    page = compare(a, b)["summary"]["pages"][0]
    assert len(page["removed"]) == 1 and len(page["added"]) == 1
    assert "الجديد" in page["removed"][0]["text"] and "القديم" in page["added"][0]["text"]


def test_report_pdf_marks_every_difference(pair):
    reply = compare(*pair, mode="text")
    report = reply["summary"]["report"]
    pages = reply["summary"]["pages"]
    with pymupdf.open(report) as doc:
        assert doc.page_count == 1 + len(pages)
        marks = [d for d in doc[2].get_drawings() if d.get("fill_opacity") == 0.25]
        clean = [d for d in doc[1].get_drawings() if d.get("fill_opacity") == 0.25]
    expected = len(pages[1]["added"]) + len(pages[1]["removed"])
    assert len(marks) == expected, (len(marks), expected)
    assert not clean, "unchanged pages carry no marks"


def test_visual_mode_measures_the_difference(tmp_path):
    a = make_text_pdf(tmp_path / "old.pdf", pages=2)
    b = edited_copy(a, tmp_path / "new.pdf", rects=[(1, (100, 500, 300, 600))])
    reply = compare(a, b, mode="visual", dpi=100)
    pages = reply["summary"]["pages"]
    assert not pages[0]["changed"] and pages[0]["difference_percent"] == 0
    second = pages[1]
    expected = 200 * 100 / (595 * 842) * 100
    assert abs(second["difference_percent"] - expected) < expected * 0.1, (second["difference_percent"], expected)
    [region] = second["regions"]
    assert abs(region[0] - 94) < 8 and abs(region[1] - 494) < 8 and abs(region[2] - 306) < 8 and abs(region[3] - 606) < 8
    image = np.asarray(Image.open(second["image"]).convert("RGB"))
    assert image.shape[:2] == (int(842 * 100 / 72), int(595 * 100 / 72))
    cy, cx = int(550 * 100 / 72), int(200 * 100 / 72)
    assert tuple(image[cy, cx]) == (20, 160, 60), "content only in the new file is green"
    assert len(reply["outputs"]) == 1 + 2  # report plus one picture per page


def test_visual_mode_shows_removed_content_in_red_and_handles_size_changes(tmp_path):
    a = make_text_pdf(tmp_path / "old.pdf", pages=1)
    b = tmp_path / "small.pdf"
    with pymupdf.open() as doc:
        doc.new_page(width=420, height=595).insert_text((72, 90), "Chapter 1 heading", fontsize=20)
        doc.save(str(b))
    page = compare(a, b, mode="visual")["summary"]["pages"][0]
    assert page["size_changed"] and page["changed"]
    image = np.asarray(Image.open(page["image"]).convert("RGB")).astype(int)
    red = ((image[:, :, 0] > 200) & (image[:, :, 1] < 60)).sum()
    assert red > 500, "the body text that only the old file has shows up red"


def test_visual_mode_pages_missing_on_one_side(tmp_path):
    a = make_text_pdf(tmp_path / "old.pdf", pages=3)
    b = edited_copy(a, tmp_path / "short.pdf", drop_last=True)
    summary = compare(a, b, mode="visual")["summary"]
    assert len(summary["pages"]) == 3
    assert summary["pages"][2]["changed"] and summary["pages"][2]["page_b"] is None
    assert summary["pages"][2]["difference_percent"] > 0.5


def test_password_protected_second_file(tmp_path):
    a = make_text_pdf(tmp_path / "old.pdf", pages=1)
    b = tmp_path / "locked.pdf"
    with pymupdf.open(a) as doc:
        doc.save(str(b), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw1", owner_pw="pw1")
    assert compare(a, b, password_b="pw1")["summary"]["changed_pages"] == 0
    from freepdf_engine.core import ToolError
    with pytest.raises(ToolError) as caught:
        compare(a, b, password_b="wrong")
    assert caught.value.code == "wrong_password"
