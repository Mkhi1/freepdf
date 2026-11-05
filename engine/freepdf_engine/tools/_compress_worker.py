"""Child process for compress: MuPDF's image rewrite is one long call with no progress or cancel hook.

Running it here lets the engine keep reporting progress and kill the work the moment the user presses Stop.
Reads {"src", "out", "password", "settings"} as JSON on stdin and writes the compressed PDF to "out".
"""
import json
import sys

from ._pdf_common import open_pdf, save_pdf


def run(request: dict) -> None:
    with open_pdf(request["src"], request.get("password")) as doc:
        doc.rewrite_images(**request["settings"])
        doc.subset_fonts()
        save_pdf(doc, request["out"], garbage=4, clean=True, deflate=True, deflate_fonts=True, use_objstms=1)


def main() -> int:
    try:
        run(json.loads(sys.stdin.read()))
    except Exception as err:
        print(f"compress worker failed: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
