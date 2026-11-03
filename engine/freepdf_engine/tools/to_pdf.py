"""Word, PowerPoint and Excel to PDF through hidden Microsoft Office."""
import shutil
from collections.abc import Callable
from pathlib import Path

from ..convert_util import file_list, merge_pdfs, scratch_dir
from ..core import Job, ToolError, output_path, result
from ..office import check_office, run_office, win_path
from ..registry import tool
from . import html_pdf, images_pdf, scan_pdf  # noqa: F401  (registers their tools)

WORD_EXTS = {".doc", ".docx", ".docm", ".rtf", ".odt", ".txt", ".dot", ".dotx"}
PPT_EXTS = {".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".odp"}
EXCEL_EXTS = {".xls", ".xlsx", ".xlsm", ".xlsb", ".csv", ".ods"}
PDF_ENDS_AT_WORD_FORMAT = 17  # wdExportFormatPDF


def _export_word(app, src: str, dest: str) -> None:
    doc = app.Documents.Open(src, False, True, False)  # name, confirm conversions, read only, recent files
    try:
        doc.ExportAsFixedFormat(dest, PDF_ENDS_AT_WORD_FORMAT, False, 0, 0, 1, 1, 0, True, True, 1, True, True, False)
    finally:
        doc.Close(0)


def _export_excel(app, src: str, dest: str) -> None:
    book = app.Workbooks.Open(src, 0, True)  # no link updates, read only
    try:
        book.ExportAsFixedFormat(0, dest, 0, True, False)
    finally:
        book.Close(False)


def _export_ppt(app, src: str, dest: str) -> None:
    deck = app.Presentations.Open(src, True, False, False)  # read only, untitled, no window
    try:
        deck.SaveAs(dest, 32)  # ppSaveAsPDF
    finally:
        deck.Close()


EXPORTERS: dict[str, tuple[str, set[str], Callable]] = {
    "word": ("Word", WORD_EXTS, _export_word),
    "excel": ("Excel", EXCEL_EXTS, _export_excel),
    "powerpoint": ("PowerPoint", PPT_EXTS, _export_ppt),
}


def _convert_one(job: Job, kind: str, src: Path, dest: Path, timeout: float) -> None:
    label, _, exporter = EXPORTERS[kind]

    def work(app):
        exporter(app, win_path(src), win_path(dest))

    run_office(kind, work, timeout, lambda: job.cancel_event.is_set())
    if not dest.exists() or dest.stat().st_size == 0:
        raise ToolError("office_failed", f"{label} did not produce a PDF for {src.name}. The file may be empty or damaged.")


def _check_extensions(kind: str, files: list[Path]) -> None:
    label, exts, _ = EXPORTERS[kind]
    for path in files:
        if path.suffix.lower() not in exts:
            raise ToolError("bad_args", f"{path.name} is not a file {label} can open.")


def convert_with_office(job: Job, args: dict, kind: str) -> dict:
    files = file_list(args)
    _check_extensions(kind, files)
    check_office(kind)
    timeout = float(args.get("timeout") or 240)
    merge = bool(args.get("merge_output")) and len(files) > 1
    out_dir = args.get("out_dir")
    work_dir = scratch_dir()
    parts: list[Path] = []
    try:
        for index, src in enumerate(files):
            job.progress(index / len(files), f"Converting {src.name}")
            part = work_dir / f"{index}.pdf"
            _convert_one(job, kind, src, part, timeout)
            parts = [*parts, part]
        outputs = _deliver(files, parts, merge, out_dir)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    job.progress(1.0, "Done")
    return result(outputs, converted=len(files))


def _deliver(files: list[Path], parts: list[Path], merge: bool, out_dir: str | None) -> list[Path]:
    if merge:
        target = output_path(files[0], "merged", ".pdf", out_dir)
        return [merge_pdfs(parts, target)]
    outputs: list[Path] = []
    for src, part in zip(files, parts):
        target = output_path(src, "", ".pdf", out_dir)
        shutil.move(str(part), target)
        outputs = [*outputs, target]
    return outputs


@tool("word_to_pdf")
def word_to_pdf(job: Job, args: dict) -> dict:
    return convert_with_office(job, args, "word")


@tool("ppt_to_pdf")
def ppt_to_pdf(job: Job, args: dict) -> dict:
    return convert_with_office(job, args, "powerpoint")


@tool("excel_to_pdf")
def excel_to_pdf(job: Job, args: dict) -> dict:
    return convert_with_office(job, args, "excel")
