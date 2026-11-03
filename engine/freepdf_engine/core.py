import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class ToolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Job:
    id: str
    emit: Callable[[dict], None]
    cancel_event: threading.Event

    def progress(self, value: float, message: str = "") -> None:
        self.check_cancelled()
        bounded = min(max(value, 0.0), 1.0)
        self.emit({"id": self.id, "type": "progress", "value": bounded, "message": message})

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise ToolError("cancelled", "Stopped.")


def result(paths: list[str | Path], **summary) -> dict:
    outputs = [{"path": str(p), "size": Path(p).stat().st_size} for p in paths]
    return {"outputs": outputs, "summary": summary}


def require(args: dict, key: str):
    if key not in args or args[key] in (None, ""):
        raise ToolError("bad_args", f"Missing option: {key}.")
    return args[key]


def require_file(path: str) -> Path:
    resolved = Path(path)
    if not resolved.is_file():
        raise ToolError("file_not_found", f"Could not find {resolved.name}. It may have been moved or deleted.")
    return resolved


def output_path(src: str | Path, label: str = "", ext: str = ".pdf", out_dir: str | None = None) -> Path:
    source = Path(src)
    folder = Path(out_dir) if out_dir else source.parent
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{source.stem} ({label})" if label else source.stem
    candidate = folder / f"{stem}{ext}"
    count = 2
    while candidate.exists():
        candidate = folder / f"{stem} {count}{ext}"
        count += 1
    return candidate


def resource_dir(name: str) -> Path:
    base = os.environ.get("FREEPDF_RES") or str(Path(os.environ["LOCALAPPDATA"]) / "FreePDF-dev")
    return Path(base) / name


def parse_ranges(spec: str, page_count: int) -> list[int]:
    pages: list[int] = []
    for part in re.split(r"[,\s]+", spec.strip()):
        if not part:
            continue
        pages = [*pages, *_parse_part(part, page_count)]
    if not pages:
        raise ToolError("bad_args", "Enter at least one page, for example 1-3,7.")
    return pages


def _parse_part(part: str, page_count: int) -> list[int]:
    match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
    if not match:
        raise ToolError("bad_args", f'"{part}" is not a page or range. Use a form like 1-3,7.')
    first = int(match.group(1))
    last = int(match.group(2) or first)
    if first < 1 or last > page_count or first > last:
        raise ToolError("bad_args", f"Pages {part} are outside this file, which has {page_count} pages.")
    return list(range(first - 1, last))
