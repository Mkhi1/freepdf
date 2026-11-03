import os
from pathlib import Path

import pytest
from samples_pages import call, difference, page_text, pymupdf, render, text_pdf

from freepdf_engine.core import ToolError


def only(res) -> Path:
    [out] = res["outputs"]
    return Path(out["path"])


def test_protect_really_encrypts_with_aes_256(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=2)
    res = call("protect", {"file": str(src), "password": "s3cret-Pass", "out_dir": str(tmp_path / "o")})
    out = only(res)
    assert res["summary"]["encryption"] == "AES-256"
    with pymupdf.open(str(out)) as doc:
        assert doc.is_encrypted and doc.needs_pass
        assert doc.authenticate("wrong") == 0
        assert doc.authenticate("s3cret-Pass") > 0
        assert "256" in doc.metadata["encryption"] and "AES" in doc.metadata["encryption"]
        assert "zebra2" in doc[1].get_text()
        assert len(doc.get_toc()) == 2
    assert b"/Encrypt" in out.read_bytes()
    assert difference(render(src, 0), render(out, 0, password="s3cret-Pass")) < 0.5


def test_protect_text_cannot_be_read_without_the_password(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=1)
    out = only(call("protect", {"file": str(src), "password": "abc123"}))
    with pymupdf.open(str(out)) as doc:
        assert doc.needs_pass
        with pytest.raises(Exception):
            doc[0].get_text()
    assert b"zebra1" not in out.read_bytes()


def test_protect_accepts_an_arabic_password(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=1)
    out = only(call("protect", {"file": str(src), "password": "كلمة-سر-123"}))
    assert "zebra1" in page_text(out, 0, password="كلمة-سر-123")


def test_protect_requires_a_password(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=1)
    with pytest.raises(ToolError) as err:
        call("protect", {"file": str(src), "password": ""})
    assert err.value.code == "bad_args"


def test_unlock_with_correct_password_removes_encryption(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=3)
    locked = only(call("protect", {"file": str(src), "password": "pw1", "out_dir": str(tmp_path / "l")}))
    res = call("unlock", {"file": str(locked), "password": "pw1", "out_dir": str(tmp_path / "u")})
    out = only(res)
    assert res["summary"]["needed_password"] is True
    with pymupdf.open(str(out)) as doc:
        assert not doc.is_encrypted and not doc.needs_pass and len(doc) == 3
        assert "zebra3" in doc[2].get_text()
    assert b"/Encrypt" not in out.read_bytes()
    assert difference(render(src, 1), render(out, 1)) < 0.5


def test_unlock_wrong_or_missing_password_is_wrong_password(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=1)
    locked = only(call("protect", {"file": str(src), "password": "right"}))
    for given in ("nope", "", None):
        with pytest.raises(ToolError) as err:
            call("unlock", {"file": str(locked), "password": given})
        assert err.value.code == "wrong_password"
    assert not list(tmp_path.glob("*unlocked*"))


def restricted_copy(src: Path, target: Path) -> Path:
    """A PDF anyone can open but that forbids copying, editing and printing (owner password only)."""
    with pymupdf.open(str(src)) as doc:
        doc.save(str(target), encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner-only", user_pw="",
                 permissions=pymupdf.PDF_PERM_ACCESSIBILITY)
    return target


def test_unlock_removes_owner_restrictions_without_a_password(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=2)
    restricted = restricted_copy(src, tmp_path / "restricted.pdf")
    with pymupdf.open(str(restricted)) as doc:
        assert not doc.needs_pass and b"/Encrypt" in restricted.read_bytes()
        assert not doc.permissions & pymupdf.PDF_PERM_COPY
        assert not doc.permissions & pymupdf.PDF_PERM_MODIFY
        assert not doc.permissions & pymupdf.PDF_PERM_PRINT
    res = call("unlock", {"file": str(restricted), "out_dir": str(tmp_path / "u")})
    out = only(res)
    assert res["summary"]["was_encrypted"] is True and res["summary"]["needed_password"] is False
    with pymupdf.open(str(out)) as doc:
        assert not doc.is_encrypted
        assert doc.permissions & pymupdf.PDF_PERM_COPY and doc.permissions & pymupdf.PDF_PERM_MODIFY
        assert doc.permissions & pymupdf.PDF_PERM_PRINT
        assert "zebra2" in doc[1].get_text()


def test_unlock_on_an_unprotected_file_just_copies_it(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=1)
    res = call("unlock", {"file": str(src), "out_dir": str(tmp_path / "u")})
    assert res["summary"]["was_encrypted"] is False
    assert "zebra1" in page_text(only(res), 0)


def test_unlock_rejects_a_file_that_is_not_a_pdf(tmp_path):
    fake = tmp_path / "x.pdf"
    fake.write_text("hello")
    with pytest.raises(ToolError) as err:
        call("unlock", {"file": str(fake)})
    assert err.value.code in ("not_a_pdf",)


def test_protect_then_unlock_round_trip_is_lossless(tmp_path):
    src = text_pdf(tmp_path / "doc.pdf", pages=4)
    locked = only(call("protect", {"file": str(src), "password": "x y z", "out_dir": str(tmp_path / "l")}))
    back = only(call("unlock", {"file": str(locked), "password": "x y z", "out_dir": str(tmp_path / "u")}))
    for page in range(4):
        assert page_text(src, page) == page_text(back, page)
        assert difference(render(src, page), render(back, page)) < 0.5
    assert os.path.getsize(back) < os.path.getsize(src) * 1.5


def _permissions_of(path, password):
    with pymupdf.open(str(path)) as doc:
        assert doc.authenticate(password)
        return doc.permissions


def test_protect_without_restrictions_keeps_every_permission(tmp_path):
    src = text_pdf(tmp_path / "plain.pdf", pages=1)
    out = only(call("protect", {"file": str(src), "password": "pw1"}))
    perms = _permissions_of(out, "pw1")
    assert perms & pymupdf.PDF_PERM_PRINT and perms & pymupdf.PDF_PERM_COPY and perms & pymupdf.PDF_PERM_MODIFY


def test_protect_can_block_printing_copying_and_editing(tmp_path):
    src = text_pdf(tmp_path / "plain.pdf", pages=1)
    args = {"file": str(src), "password": "pw1", "allow_print": False, "allow_copy": False, "allow_modify": False}
    res = call("protect", args)
    assert res["summary"]["restricted"] is True
    perms = _permissions_of(only(res), "pw1")
    assert not perms & pymupdf.PDF_PERM_PRINT
    assert not perms & pymupdf.PDF_PERM_COPY
    assert not perms & pymupdf.PDF_PERM_MODIFY


def test_protect_blocks_only_what_was_switched_off(tmp_path):
    src = text_pdf(tmp_path / "plain.pdf", pages=1)
    out = only(call("protect", {"file": str(src), "password": "pw1", "allow_print": True, "allow_copy": True, "allow_modify": False}))
    perms = _permissions_of(out, "pw1")
    assert perms & pymupdf.PDF_PERM_PRINT and perms & pymupdf.PDF_PERM_COPY
    assert not perms & pymupdf.PDF_PERM_MODIFY


def test_protect_opens_a_locked_file_with_current_password(tmp_path):
    src = text_pdf(tmp_path / "plain.pdf", pages=1)
    locked = only(call("protect", {"file": str(src), "password": "old-pw"}))
    out = only(call("protect", {"file": str(locked), "current_password": "old-pw", "password": "new-pw"}))
    with pymupdf.open(str(out)) as doc:
        assert not doc.authenticate("old-pw")
        assert doc.authenticate("new-pw")
    with pytest.raises(ToolError) as err:
        call("protect", {"file": str(locked), "password": "new-pw"})
    assert err.value.code == "wrong_password"
