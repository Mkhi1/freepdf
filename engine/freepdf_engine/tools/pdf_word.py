"""PDF to Word. Two engines: Word's own PDF import and pdf2docx, used in the order the evaluation favoured."""
import shutil
from pathlib import Path

from ..convert_util import open_pdf, scratch_dir
from ..core import Job, ToolError, output_path, require, result
from ..office import check_office, run_office, win_path
from ..registry import tool
from .docx_ocr import write_docx_from_text
from .docx_rtl import fix_rtl_docx
from .docx_text import docx_text, fix_persian_forms, is_mostly_arabic, pdf_words_text, recall
from .pdf_ocr import ocr_input

WD_FORMAT_DEFAULT = 16  # wdFormatDocumentDefault (.docx)


def word_import(src: Path, dest: Path, timeout: float = 240, cancelled=None) -> None:
    """Open the PDF in a hidden Word (no conversion prompt) and save it as .docx."""
    def work(app):
        doc = app.Documents.Open(win_path(src), False, True, False)  # confirm conversions off, read only, no recent file
        try:
            doc.SaveAs2(win_path(dest), WD_FORMAT_DEFAULT)
        finally:
            doc.Close(0)

    run_office("word", work, timeout, cancelled)


def pdf2docx_convert(src: Path, dest: Path, password: str | None = None) -> None:
    import logging
    from pdf2docx import Converter
    logging.getLogger().setLevel(logging.WARNING)  # pdf2docx logs progress through the root logger
    converter = Converter(str(src), password=password or None)
    try:
        converter.convert(str(dest))
    finally:
        converter.close()


def _run_engine(engine: str, src: Path, dest: Path, job: Job, password: str | None) -> None:
    if engine == "word":
        check_office("word")
        word_import(src, dest, cancelled=lambda: job.cancel_event.is_set())
        fix_persian_forms(dest)
    else:
        pdf2docx_convert(src, dest, password)
        if dest.exists():
            fix_rtl_docx(dest)
    if not dest.exists() or dest.stat().st_size == 0:
        raise ToolError("tool_failed", "The converter produced an empty file.")


# Measured on generated samples (see the report): pdf2docx keeps the page layout best but can drop
# spaces between styled runs and loses columns in Arabic tables; Word's import keeps text exact but reflows.
TEXT_GATE = 0.98


def engine_order(reference: str, forced: tuple[str, ...] | None) -> tuple[str, ...]:
    if forced:
        return forced
    return ("word", "pdf2docx") if is_mostly_arabic(reference) else ("pdf2docx", "word")


def convert_to_docx(job: Job, src: Path, dest: Path, password: str | None, forced: tuple[str, ...] | None = None) -> tuple[str, float]:
    reference = pdf_words_text(src, password)
    best: tuple[str, float, Path] | None = None
    for engine in engine_order(reference, forced):
        job.check_cancelled()
        attempt = dest.with_name(f"{engine}-{dest.name}")
        try:
            _run_engine(engine, src, attempt, job, password)
        except ToolError as err:
            if err.code == "cancelled":
                raise
            continue
        except Exception:
            continue
        score = recall(reference, docx_text(attempt))
        if best is None or score > best[1]:
            best = (engine, score, attempt)
        if score >= TEXT_GATE:
            break
    if best is None:
        raise ToolError("tool_failed", "This PDF could not be converted to Word. If it is a scan, turn on text recognition and try again.")
    shutil.move(str(best[2]), dest)
    return best[0], round(best[1], 4)


def _from_recognised_text(prepared: Path, draft: Path) -> tuple[str, float]:
    """Scans: Word's import keeps only the picture and pdf2docx finds no words, so build from the OCR text."""
    write_docx_from_text(prepared, draft)
    return "ocr_text", round(recall(pdf_words_text(prepared), docx_text(draft)), 4)


@tool("pdf_to_word")
def pdf_to_word(job: Job, args: dict) -> dict:
    source = Path(require(args, "file"))
    password = args.get("password")
    open_pdf(str(source), password).close()
    work_dir = scratch_dir()
    try:
        job.progress(0.05, "Preparing")
        prepared = ocr_input(job, source, args, work_dir)
        job.progress(0.2, "Converting to Word")
        draft = work_dir / "out.docx"
        if prepared != source:
            engine, score = _from_recognised_text(prepared, draft)
        else:
            forced = tuple(args["engines"]) if args.get("engines") else None
            engine, score = convert_to_docx(job, prepared, draft, password, forced)
        target = output_path(source, "", ".docx", args.get("out_dir"))
        shutil.move(str(draft), target)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    job.progress(1.0, "Done")
    return result([target], engine=engine, text_recall=score)
