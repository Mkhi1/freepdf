import sys

__version__ = "0.1.0"

# PyMuPDF loads an AI page-layout model on import, which adds over a second to every start. No tool uses it.
sys.modules.setdefault("pymupdf.layout", None)
sys.modules.setdefault("pymupdf4llm", None)
