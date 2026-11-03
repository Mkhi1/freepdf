"""Decides whether recognised text is good enough to replace a page picture with editable text.

The OCR engine reports no confidence, so this judges the words themselves. Being wrong in the strict direction
only leaves a perfect picture on the slide; being wrong the other way erases the page and prints garbage on it.

Only left-to-right words count. Arabic comes back from OCR with its sentence parts out of order however well
each word is read, so an Arabic page never qualifies.
"""
import re
from collections.abc import Iterable

MIN_TRUSTED_SHARE = 0.93  # on real pages poor reads reached 80% and clean reads scored 98% or more
MIN_WORD_LETTERS = 2
EDGE_MARKS = "\"'“”‘’«»()[]{}.,:;!?،؛؟-–—_…/\\|*•"
ARABIC_LETTER = re.compile("[؀-ۿݐ-ݿﭐ-﷿ﹰ-ﻼ]")
INNER_JOINERS = re.compile("['’.\\-–—]")
WEB_ADDRESS = re.compile(r"@|://|^www\.|\.[a-z]{2,}$", re.I)


def _says_nothing(core: str) -> bool:
    """Numbers, codes, symbols and web addresses can be read correctly without looking like words."""
    return not any(c.isalpha() for c in core) or any(c.isdigit() for c in core) or bool(WEB_ADDRESS.search(core))


def _reads_well(letters: str) -> bool:
    return len(letters) >= MIN_WORD_LETTERS and letters.isalpha() and not ARABIC_LETTER.search(letters)


def reading_share(words: Iterable[str]) -> float:
    """Share of the letters on a page that sit in properly read left-to-right words."""
    cores = (word.strip(EDGE_MARKS) for word in words)
    found = [INNER_JOINERS.sub("", core) for core in cores if not _says_nothing(core)]
    total = sum(len(letters) for letters in found)
    return sum(len(letters) for letters in found if _reads_well(letters)) / total if total else 0.0


def reading_is_trustworthy(words: Iterable[str]) -> bool:
    return reading_share(words) >= MIN_TRUSTED_SHARE
