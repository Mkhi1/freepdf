"""Text checks and repairs for generated .docx files."""
import re
import shutil
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

import pymupdf

# Word's PDF import writes Persian letter forms for Arabic words. When the document has no
# Persian-only letters these are plain Arabic mistakes, so map them back.
PERSIAN_ONLY = "پچژگ"
FIX_MAP = {"ی": "ي", "ھ": "ه", "ک": "ك", "ہ": "ه", "ے": "ي"}
ARABIC_RANGE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
TEXT_RUN = re.compile(r"<w:t(?: [^>]*)?>([^<]*)</w:t>")


def pdf_words_text(path: Path, password: str | None = None, max_pages: int | None = None) -> str:
    with pymupdf.open(str(path)) as doc:
        if doc.needs_pass:
            doc.authenticate(password or "")
        pages = list(doc)[:max_pages] if max_pages else list(doc)
        return "\n".join(page.get_text() for page in pages)


def is_mostly_arabic(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if ARABIC_RANGE.match(c)) / len(letters) > 0.3


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>|<w:br[^>]*/>|<w:tab/>", "<w:t> </w:t>", xml)
    return "".join(TEXT_RUN.findall(xml))  # runs inside a paragraph are contiguous text


def _canon(word: str) -> str:
    word = unicodedata.normalize("NFKC", word)
    word = word.replace("لا", "ال")  # PDF extraction may swap the lam-alef pair
    word = "".join(ch for ch in word if unicodedata.category(ch)[0] in "LN")
    return min(word, word[::-1])


def _bag(text: str) -> Counter:
    return Counter(w for w in (_canon(t) for t in text.split()) if w)


def recall(reference: str, candidate: str) -> float:
    ref = _bag(reference)
    total = sum(ref.values())
    if not total:
        return 1.0
    return sum((ref & _bag(candidate)).values()) / total


def fix_persian_forms(docx_path: Path) -> None:
    """Rewrite the .docx in place, replacing Persian letter forms when the text is Arabic."""
    text = docx_text(docx_path)
    if not is_mostly_arabic(text) or any(ch in text for ch in PERSIAN_ONLY):
        return
    table = str.maketrans(FIX_MAP)
    patched = docx_path.with_suffix(".fixed")
    with zipfile.ZipFile(docx_path) as source, zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                data = data.decode("utf-8").translate(table).encode("utf-8")
            target.writestr(item, data)
    shutil.move(str(patched), docx_path)
