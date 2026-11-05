"""Optimize tools: compress, repair, pdfa, ocr."""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ..core import Job, ToolError, output_path, require, require_file, resource_dir, result
from ..registry import tool
from ._ocr_layer import build_font_bytes, recognise, tessdata_path, write_words
from ._pdf_common import check_pages, open_pdf, pymupdf, save_pdf
from ._pdf_rebuild import rebuild_tail

# dpi_threshold: images sharper than this are scaled down to dpi_target. quality: JPEG quality.
COMPRESS_LEVELS = {
    "less": {"dpi_threshold": 250, "dpi_target": 220, "quality": 85},
    "recommended": {"dpi_threshold": 170, "dpi_target": 144, "quality": 70},
    "extreme": {"dpi_threshold": 100, "dpi_target": 72, "quality": 40},
}


# Rough cost of the image rewrite, used only to pace the progress bar while the child process works.
SECONDS_PER_MEGAPIXEL = 0.08
SECONDS_PER_IMAGE = 0.05
STARTUP_SECONDS = 1.0
POLL_SECONDS = 0.1
REPORT_EVERY_SECONDS = 0.4


def _estimate_seconds(doc) -> float:
    seen, pixels = set(), 0
    for page in doc:
        for image in page.get_images(full=True):
            if image[0] not in seen:
                seen.add(image[0])
                pixels += image[2] * image[3]
    return STARTUP_SECONDS + SECONDS_PER_MEGAPIXEL * pixels / 1e6 + SECONDS_PER_IMAGE * len(seen)


def _paced_progress(elapsed: float, estimate: float) -> tuple[float, str]:
    """Climbs steadily toward 90% and never stalls or claims to be done early."""
    value = 0.05 + 0.85 * (1 - math.exp(-elapsed / estimate))
    message = "Recompressing images" if elapsed < 1.5 * estimate else "Still working. Big pictures take a while"
    return value, message


def _compress_in_child(job: Job, request: dict, estimate: float) -> None:
    flags = (NO_WINDOW | BELOW_NORMAL) if sys.platform == "win32" else 0
    package_root = Path(__file__).resolve().parents[2]
    proc = subprocess.Popen(
        [sys.executable, "-m", "freepdf_engine.tools._compress_worker"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        cwd=str(package_root), creationflags=flags,
    )
    try:
        proc.stdin.write(json.dumps(request).encode("utf-8"))
        proc.stdin.close()
        started = last_report = time.monotonic()
        while proc.poll() is None:
            now = time.monotonic()
            if now - last_report >= REPORT_EVERY_SECONDS:
                job.progress(*_paced_progress(now - started, estimate))
                last_report = now
            job.check_cancelled()
            time.sleep(POLL_SECONDS)
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.read().decode("utf-8", "replace"))
        raise ToolError("tool_failed", "Free PDF could not compress this file. It may be damaged. Try Repair a PDF first.")


@tool("compress")
def compress(job: Job, args: dict) -> dict:
    src = require_file(require(args, "file"))
    level = args.get("level") or "recommended"
    if level not in COMPRESS_LEVELS:
        raise ToolError("bad_args", "Compression level must be extreme, recommended or less.")
    before = src.stat().st_size
    with tempfile.TemporaryDirectory(prefix="freepdf-compress-") as scratch:
        candidate = Path(scratch) / "out.pdf"
        job.progress(0.02, "Looking at the pictures")
        with open_pdf(src, args.get("password")) as doc:
            estimate = _estimate_seconds(doc)
        request = {"src": str(src), "out": str(candidate), "password": args.get("password"),
                   "settings": COMPRESS_LEVELS[level]}
        _compress_in_child(job, request, estimate)
        job.progress(0.95, "Saving")
        out_path = output_path(src, "compressed", out_dir=args.get("out_dir"))
        after = candidate.stat().st_size
        smaller = after < before
        shutil.copyfile(candidate if smaller else src, out_path)
    final = out_path.stat().st_size
    percent = round(100 * (before - final) / before, 1) if before else 0.0
    note = "" if smaller else "This file is already as small as it can get, so it was copied unchanged."
    return result([out_path], before=before, after=final, percent=percent, level=level, unchanged=not smaller, note=note)


# --- repair ----------------------------------------------------------------

def _readable_pages(doc) -> list[int]:
    good = []
    for index in range(len(doc)):
        try:
            doc[index].get_text("text")
            doc[index].get_pixmap(dpi=8, alpha=False)
            good.append(index)
        except Exception:
            continue
    return good


def _open_damaged(src: Path, password):
    """Open normally; if the file's end is missing, rebuild a page tree from the surviving objects."""
    try:
        return open_pdf(src, password)
    except ToolError as err:
        if err.code != "not_a_pdf":
            raise
    rebuilt = rebuild_tail(src.read_bytes())
    try:
        doc = pymupdf.open(stream=rebuilt, filetype="pdf") if rebuilt else None
    except Exception:
        doc = None
    if doc is None or len(doc) == 0:
        raise ToolError("tool_failed", f"{src.name} is too damaged to recover. No readable pages were found.")
    return doc


def _save_repaired(doc, out_path: Path) -> None:
    """Save with a full clean-up; a badly broken file can refuse that, so fall back to gentler saves."""
    for options in ({"garbage": 4, "clean": True}, {"garbage": 1}, {"garbage": 0}):
        try:
            save_pdf(doc, out_path, **options)
            return
        except Exception:
            out_path.unlink(missing_ok=True)
    raise ToolError("tool_failed", f"{out_path.name} is too damaged to save a repaired copy.")


@tool("repair")
def repair(job: Job, args: dict) -> dict:
    src = require_file(require(args, "file"))
    doc = _open_damaged(src, args.get("password"))
    with doc:
        total = len(doc)
        if total == 0:
            raise ToolError("tool_failed", f"{src.name} is too damaged to recover. No pages could be found.")
        job.progress(0.3, "Checking pages")
        good = _readable_pages(doc)
        if not good:
            raise ToolError("tool_failed", f"No page in {src.name} could be read, so it cannot be repaired.")
        out_path = output_path(src, "repaired", out_dir=args.get("out_dir"))
        job.progress(0.7, "Rebuilding file")
        if len(good) == total:
            _save_repaired(doc, out_path)
        else:
            rebuilt = pymupdf.open()
            for index in good:
                rebuilt.insert_pdf(doc, from_page=index, to_page=index)
            _save_repaired(rebuilt, out_path)
            rebuilt.close()
    return result([out_path], pages_total=total, pages_recovered=len(good), pages_lost=total - len(good),
                  was_repaired=True)


# --- PDF/A ---------------------------------------------------------------------

PDFA_PARTS = {"1b": 1, "2b": 2, "3b": 3}
GS_MISSING = (
    "PDF/A conversion needs Ghostscript, which is not installed with Free PDF yet. "
    "Install Ghostscript or place it in the app's tools folder (tools\\gs\\bin\\gswin64c.exe)."
)
BELOW_NORMAL = 0x4000
NO_WINDOW = 0x08000000
GS_TIMEOUT_SECONDS = 900


def find_ghostscript() -> Path | None:
    bundled = resource_dir("tools") / "gs" / "bin" / "gswin64c.exe"
    if bundled.is_file():
        return bundled
    on_path = shutil.which("gswin64c")
    if on_path:
        return Path(on_path)
    installed = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "gs"
    versions = sorted(installed.glob("gs*/bin/gswin64c.exe"), reverse=True)
    return versions[0] if versions else None


def _icc_profile(gs: Path) -> Path:
    root = gs.parent.parent
    for folder in (root / "iccprofiles", root / "lib", gs.parent / "iccprofiles"):
        for name in ("default_rgb.icc", "srgb.icc"):
            if (folder / name).is_file():
                return folder / name
    raise ToolError("missing_resource", "Ghostscript was found but its colour profile (default_rgb.icc) is missing.")


def _pdfa_definition(icc: Path) -> str:
    profile = str(icc).replace("\\", "/").replace("(", "\\(").replace(")", "\\)")
    return (
        f"/ICCProfile ({profile}) def\n"
        "[/_objdef {icc_PDFA} /type /stream /OBJ pdfmark\n"
        "[{icc_PDFA} <</N 3>> /PUT pdfmark\n"
        "[{icc_PDFA} ICCProfile (r) file /PUT pdfmark\n"
        "[/_objdef {OutputIntent_PDFA} /type /dict /OBJ pdfmark\n"
        "[{OutputIntent_PDFA} <</Type /OutputIntent /S /GTS_PDFA1 /DestOutputProfile {icc_PDFA}"
        " /OutputConditionIdentifier (sRGB)>> /PUT pdfmark\n"
        "[{Catalog} <</OutputIntents [{OutputIntent_PDFA}]>> /PUT pdfmark\n"
    )


def _run_ghostscript(job: Job, command: list[str]) -> None:
    flags = (NO_WINDOW | BELOW_NORMAL) if sys.platform == "win32" else 0
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)
    started = time.monotonic()
    while proc.poll() is None:
        try:
            job.check_cancelled()
        except ToolError:
            proc.kill()
            raise
        if time.monotonic() - started > GS_TIMEOUT_SECONDS:
            proc.kill()
            raise ToolError("tool_failed", "PDF/A conversion took too long and was stopped.")
        time.sleep(0.2)
    if proc.returncode != 0:
        raise ToolError("tool_failed", "Ghostscript could not convert this file to PDF/A. The file may be damaged.")


@tool("pdfa")
def pdfa(job: Job, args: dict) -> dict:
    src = require_file(require(args, "file"))
    conformance = args.get("conformance") or "2b"
    if conformance not in PDFA_PARTS:
        raise ToolError("bad_args", "Conformance must be 1b, 2b or 3b.")
    gs = find_ghostscript()
    if gs is None:
        raise ToolError("missing_resource", GS_MISSING)
    out_path = output_path(src, f"PDFA-{conformance}", out_dir=args.get("out_dir"))
    with tempfile.TemporaryDirectory(prefix="freepdf-pdfa-") as scratch:
        icc = _icc_profile(gs)
        definition = Path(scratch) / "PDFA_def.ps"
        definition.write_text(_pdfa_definition(icc), encoding="utf-8")
        plain = _plain_copy(src, args.get("password"), Path(scratch) / "in.pdf")
        # Ghostscript reads % in an output name as a page pattern, so it always writes to a plain temp name.
        converted = Path(scratch) / "out.pdf"
        job.progress(0.2, "Converting to PDF/A")
        _run_ghostscript(job, [
            str(gs), f"-dPDFA={PDFA_PARTS[conformance]}", "-dBATCH", "-dNOPAUSE", "-dQUIET",
            f"--permit-file-read={icc.as_posix()}",
            "-sColorConversionStrategy=RGB", "-sProcessColorModel=DeviceRGB", "-dPDFACompatibilityPolicy=1",
            "-sDEVICE=pdfwrite", f"-sOutputFile={converted}", str(definition), str(plain),
        ])
        shutil.move(converted, out_path)
    _verify_pdfa(out_path, conformance)
    return result([out_path], conformance=conformance)


def _plain_copy(src: Path, password, target: Path) -> Path:
    with open_pdf(src, password) as doc:
        save_pdf(doc, target, garbage=1, encryption=pymupdf.PDF_ENCRYPT_NONE)
    return target


def pdfa_part(xmp: str | None) -> int | None:
    """Read the PDF/A part from XMP, written either as an attribute or as an element."""
    found = re.search(r"pdfaid:part(?:=['\"]|>)(\d)", xmp or "")
    return int(found.group(1)) if found else None


def _verify_pdfa(path: Path, conformance: str) -> None:
    with pymupdf.open(str(path)) as doc:
        part = pdfa_part(doc.get_xml_metadata())
    if part != PDFA_PARTS[conformance]:
        path.unlink(missing_ok=True)
        raise ToolError("tool_failed", "The converted file is not marked as PDF/A, so it was discarded.")


# --- OCR -------------------------------------------------------------------------------

MIN_EXISTING_TEXT = 20


@tool("ocr")
def ocr(job: Job, args: dict) -> dict:
    src = require_file(require(args, "file"))
    languages = args.get("languages") or ["eng", "ara"]
    tessdata = tessdata_path(languages)
    with open_pdf(src, args.get("password")) as doc:
        pages = check_pages(args.get("pages"), len(doc))
        found, skipped = {}, []
        for number, index in enumerate(pages):
            job.progress(0.9 * number / len(pages), f"Reading page {number + 1} of {len(pages)}")
            page = doc[index]
            if not args.get("force") and len(page.get_text("text").strip()) >= MIN_EXISTING_TEXT:
                skipped.append(index)
                continue
            found[index] = recognise(page, languages, tessdata)
        out_path = output_path(src, "OCR", out_dir=args.get("out_dir"))
        _write_layer(job, doc, found)
        save_pdf(doc, out_path, garbage=4, deflate=True)
    words = sum(len(w) for w in found.values())
    return result([out_path], pages_read=len(found), pages_skipped=len(skipped), words=words)


def _write_layer(job: Job, doc, found: dict[int, list[tuple]]) -> None:
    if not any(found.values()):
        return
    job.progress(0.92, "Adding text layer")
    font_bytes = build_font_bytes(list(found.values()))
    font = pymupdf.Font(fontbuffer=font_bytes)
    for index, words in found.items():
        write_words(doc[index], words, font_bytes, font)
