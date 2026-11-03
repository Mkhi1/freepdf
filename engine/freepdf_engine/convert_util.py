"""Small helpers shared by the conversion tools."""
import tempfile
import zipfile
from pathlib import Path

import pymupdf

from .core import ToolError, require, require_file


def open_pdf(path: str, password: str | None = None) -> pymupdf.Document:
    src = require_file(path)
    try:
        doc = pymupdf.open(str(src))
    except Exception:
        raise ToolError("not_a_pdf", f"{src.name} is not a PDF or is damaged.")
    if doc.needs_pass and not doc.authenticate(password or ""):
        doc.close()
        raise ToolError("wrong_password", f"{src.name} is protected. Enter the right password.")
    return doc


def file_list(args: dict, key: str = "files") -> list[Path]:
    items = require(args, key)
    if not isinstance(items, list) or not items:
        raise ToolError("bad_args", "Add at least one file.")
    return [require_file(item["path"] if isinstance(item, dict) else item) for item in items]


def zip_files(paths: list[Path], target: Path) -> Path:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as archive:
        for path in paths:
            archive.write(path, path.name)
    return target


def scratch_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="freepdf-"))


def merge_pdfs(paths: list[Path], target: Path) -> Path:
    merged = pymupdf.open()
    try:
        for path in paths:
            with pymupdf.open(str(path)) as part:
                merged.insert_pdf(part)
        merged.save(str(target), garbage=3, deflate=True)
    finally:
        merged.close()
    return target
