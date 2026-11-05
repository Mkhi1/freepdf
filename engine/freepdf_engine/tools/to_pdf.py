"""Word, PowerPoint and Excel to PDF through hidden Microsoft Office, or through Edge when Office is not installed."""
import shutil
from collections.abc import Callable
from pathlib import Path

from ..convert_util import file_list, merge_pdfs, scratch_dir
from ..core import Job, ToolError, output_path, result
from ..office import check_office, run_office, win_path
from ..registry import tool
from . import html_pdf, images_pdf, scan_pdf  # noqa: F401  (registers their tools)
from ._html_common import document, esc, text_dir
from ._html_docx import docx_to_html
from ._html_sheet import sheet_to_html
from ._html_slides import slides_to_html

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


def _text_to_html(src: Path) -> str:
    text = src.read_bytes().decode("utf-8-sig", errors="replace")
    paras = "".join(f'<p dir="{text_dir(line)}">{esc(line) or "&nbsp;"}</p>' for line in text.splitlines())
    return document(paras, "@page{size:8.27in 11.69in;margin:1in}body{font-family:Calibri,Arial;font-size:11pt;line-height:1.3}")


# Formats rebuilt as HTML and printed by Edge when Office is missing. Old binary formats need Office.
WITHOUT_OFFICE: dict[str, Callable[[Path], str]] = {
    ".docx": docx_to_html, ".docm": docx_to_html, ".dotx": docx_to_html, ".txt": _text_to_html,
    ".xlsx": sheet_to_html, ".xlsm": sheet_to_html, ".csv": sheet_to_html,
    ".pptx": slides_to_html, ".pptm": slides_to_html, ".ppsx": slides_to_html,
}


def _office_installed(kind: str) -> bool:
    try:
        check_office(kind)
        return True
    except ToolError:
        return False


def _convert_without_office(job: Job, kind: str, src: Path, dest: Path) -> None:
    builder = WITHOUT_OFFICE.get(src.suffix.lower())
    if builder is None:
        label = EXPORTERS[kind][0]
        raise ToolError("office_missing", f"{src.name} is an older {label} format that needs Microsoft {label}. "
                        f"Save it as {'.docx' if kind == 'word' else '.xlsx' if kind == 'excel' else '.pptx'} and try again.")
    try:
        page_html = builder(src)
    except ToolError:
        raise
    except Exception:
        raise ToolError("office_failed", f"{src.name} could not be read. The file may be damaged or password protected.")
    page = dest.with_suffix(".html")
    page.write_text(page_html, encoding="utf-8")
    dest.write_bytes(html_pdf.print_html_file(job, page))


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
    with_office = _office_installed(kind)
    timeout = float(args.get("timeout") or 240)
    merge = bool(args.get("merge_output")) and len(files) > 1
    out_dir = args.get("out_dir")
    work_dir = scratch_dir()
    parts: list[Path] = []
    try:
        for index, src in enumerate(files):
            job.progress(index / len(files), f"Converting {src.name}")
            part = work_dir / f"{index}.pdf"
            if with_office:
                _convert_one(job, kind, src, part, timeout)
            else:
                _convert_without_office(job, kind, src, part)
            parts = [*parts, part]
        outputs = _deliver(files, parts, merge, out_dir)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    job.progress(1.0, "Done")
    return result(outputs, converted=len(files), engine="office" if with_office else "edge")


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
