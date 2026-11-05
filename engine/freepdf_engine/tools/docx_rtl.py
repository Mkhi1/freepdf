"""Right-to-left repairs for .docx files written by pdf2docx, which marks nothing as Arabic.

Without these, Word lays Arabic paragraphs out left to right, sizes Arabic letters at the default
complex-script size, and runs an Arabic line straight into the English line after it.
"""
import shutil
import zipfile
from pathlib import Path

from lxml import etree

from .docx_text import ARABIC_RANGE

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
BEFORE_BIDI = ("adjustRightInd", "snapToGrid", "spacing", "ind", "contextualSpacing", "jc", "textDirection", "rPr")


def _q(tag: str) -> str:
    return f"{{{W}}}{tag}"


def _letters(text: str) -> tuple[int, int]:
    arabic = sum(1 for c in text if ARABIC_RANGE.match(c))
    latin = sum(1 for c in text if c.isalpha()) - arabic
    return arabic, latin


def _script(text: str) -> str | None:
    arabic, latin = _letters(text)
    if not arabic and not latin:
        return None
    return "ar" if arabic >= latin else "la"


def _child(parent, tag: str, before: tuple[str, ...] = ()):
    found = parent.find(f"w:{tag}", NS)
    if found is not None:
        return found
    node = etree.Element(_q(tag))
    anchor = next((parent.find(f"w:{name}", NS) for name in before if parent.find(f"w:{name}", NS) is not None), None)
    if anchor is not None:
        anchor.addprevious(node)
    else:
        parent.append(node)
    return node


def _mark_run_rtl(run) -> None:
    rpr = run.find("w:rPr", NS)
    if rpr is None:
        rpr = etree.Element(_q("rPr"))
        run.insert(0, rpr)
    fonts = rpr.find("w:rFonts", NS)
    if fonts is not None and fonts.get(_q("cs")) is None:
        fonts.set(_q("cs"), fonts.get(_q("ascii")) or "Arial")
    size = rpr.find("w:sz", NS)
    if size is not None and rpr.find("w:szCs", NS) is None:
        size.addnext(etree.Element(_q("szCs"), {_q("val"): size.get(_q("val"))}))
    bold = rpr.find("w:b", NS)
    if bold is not None and bold.get(_q("val")) not in ("0", "false") and rpr.find("w:bCs", NS) is None:
        bold.addnext(etree.Element(_q("bCs")))
    _child(rpr, "rtl", ("cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath"))


def _run_text(run) -> str:
    return "".join(t.text or "" for t in run.findall("w:t", NS))


def _split_glued(runs: list) -> None:
    """A run of one script that touches a run of the other with no space between is two lines pdf2docx joined."""
    for left, right in zip(runs, runs[1:]):
        a, b = _run_text(left), _run_text(right)
        if a and b and not a[-1].isspace() and not b[0].isspace() and {_script(a), _script(b)} == {"ar", "la"}:
            left.append(etree.Element(_q("br")))


def _fix_paragraph(paragraph) -> None:
    runs = paragraph.findall("w:r", NS)
    texts = [_run_text(r) for r in runs]
    _split_glued(runs)
    for run, text in zip(runs, texts):
        if _script(text) == "ar":
            _mark_run_rtl(run)
    if _script("".join(texts)) != "ar":
        return
    ppr = paragraph.find("w:pPr", NS)
    if ppr is None:
        ppr = etree.Element(_q("pPr"))
        paragraph.insert(0, ppr)
    _child(ppr, "bidi", BEFORE_BIDI)
    justify = ppr.find("w:jc", NS)
    if justify is not None and justify.get(_q("val")) in ("left", "start"):
        ppr.remove(justify)  # a right-to-left paragraph starts on the right by default
    for run in runs:  # leading tabs only pushed the line to the right edge
        if _run_text(run) or run.find("w:tab", NS) is None:
            break
        paragraph.remove(run)


def fix_rtl_docx(docx_path: Path) -> bool:
    """Rewrites the .docx in place. Returns whether it held any Arabic."""
    with zipfile.ZipFile(docx_path) as source:
        xml = source.read("word/document.xml")
    if not ARABIC_RANGE.search(xml.decode("utf-8", "replace")):
        return False
    root = etree.fromstring(xml)
    for paragraph in root.iter(_q("p")):
        _fix_paragraph(paragraph)
    patched = docx_path.with_suffix(".rtl")
    with zipfile.ZipFile(docx_path) as source, zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/document.xml":
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(item, data)
    shutil.move(str(patched), docx_path)
    return True
