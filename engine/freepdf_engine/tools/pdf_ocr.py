"""Optional OCR pass shared by the PDF export tools (uses the `ocr` tool when it is registered)."""
from pathlib import Path

from ..core import Job, ToolError
from ..registry import TOOLS


def ocr_input(job: Job, source: Path, args: dict, work_dir: Path) -> Path:
    """Return the PDF to convert: the OCR'd copy when args.ocr is set, otherwise the source."""
    if not args.get("ocr"):
        return source
    ocr = TOOLS.get("ocr")
    if ocr is None:
        raise ToolError("tool_failed", "Text recognition is not available in this build. Turn it off and try again.")
    languages = args.get("languages") or ["eng", "ara"]
    outcome = ocr(job, {"file": str(source), "languages": languages, "password": args.get("password"), "out_dir": str(work_dir)})
    outputs = outcome.get("outputs") or []
    if not outputs:
        raise ToolError("tool_failed", "Text recognition did not produce a result.")
    return Path(outputs[0]["path"])
