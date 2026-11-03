"""Scanner access through Windows Image Acquisition (WIA), without any scanner dialog.

Not testable without a physical scanner; the code follows the documented WIA 2.0 automation API.
"""
import io
import os
from pathlib import Path

import pymupdf
from PIL import Image

from ..core import Job, ToolError, output_path, result
from ..registry import tool

SCANNER_TYPE = 1
FORMAT_BMP = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"
INTENT_COLOR, INTENT_GRAY = 1, 2
PROP_INTENT, PROP_XRES, PROP_YRES = 6146, 6147, 6148
PROP_XPOS, PROP_YPOS, PROP_XEXT, PROP_YEXT = 6149, 6150, 6151, 6152
A4_INCHES = (8.27, 11.69)
NO_SCANNER = "No scanner was found. Connect and turn on your scanner, then try again."


def _manager():
    import win32com.client
    return win32com.client.Dispatch("WIA.DeviceManager")


def _scanners(manager) -> list[dict]:
    found = []
    for index in range(1, manager.DeviceInfos.Count + 1):
        info = manager.DeviceInfos.Item(index)
        if info.Type == SCANNER_TYPE:
            found.append({"id": str(info.DeviceID), "name": str(info.Properties("Name").Value)})
    return found


def _com_call(fn):
    import pythoncom
    pythoncom.CoInitialize()
    try:
        return fn()
    except ToolError:
        raise
    except Exception as err:
        raise ToolError("tool_failed", f"The scanner reported a problem: {_reason(err)}")
    finally:
        pythoncom.CoUninitialize()


def _reason(err: Exception) -> str:
    details = getattr(err, "excepinfo", None)
    if details and len(details) > 2 and details[2]:
        return str(details[2]).strip()
    return str(err).splitlines()[0] if str(err) else type(err).__name__


@tool("list_scanners")
def list_scanners(job: Job, args: dict) -> dict:
    devices = _com_call(lambda: _scanners(_manager()))
    return {"outputs": [], "summary": {"devices": devices}}


def _set(item, prop_id: int, value: int) -> None:
    item.Properties(prop_id).Value = value


def _scan_image(device_id: str | None, dpi: int, color: bool) -> Image.Image:
    manager = _manager()
    scanners = _scanners(manager)
    if not scanners:
        raise ToolError("tool_failed", NO_SCANNER)
    chosen = next((s for s in scanners if s["id"] == device_id), None) if device_id else scanners[0]
    if chosen is None:
        raise ToolError("bad_args", "That scanner is no longer connected. Choose another one.")
    item = next(i for i in manager.DeviceInfos if i.DeviceID == chosen["id"]).Connect().Items(1)
    _set(item, PROP_INTENT, INTENT_COLOR if color else INTENT_GRAY)
    _set(item, PROP_XRES, dpi)
    _set(item, PROP_YRES, dpi)
    _set(item, PROP_XPOS, 0)
    _set(item, PROP_YPOS, 0)
    _set(item, PROP_XEXT, round(A4_INCHES[0] * dpi))
    _set(item, PROP_YEXT, round(A4_INCHES[1] * dpi))
    image = item.Transfer(FORMAT_BMP)
    return Image.open(io.BytesIO(bytes(image.FileData.BinaryData))).convert("RGB" if color else "L")


@tool("scan_to_pdf")
def scan_to_pdf(job: Job, args: dict) -> dict:
    dpi = int(args.get("dpi") or 300)
    if not 75 <= dpi <= 1200:
        raise ToolError("bad_args", "Resolution must be between 75 and 1200 dpi.")
    color = bool(args.get("color", True))
    job.progress(0.1, "Scanning")
    image = _com_call(lambda: _scan_image(args.get("device"), dpi, color))
    job.progress(0.8, "Saving the PDF")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90, dpi=(dpi, dpi))
    width_pt, height_pt = image.width * 72.0 / dpi, image.height * 72.0 / dpi
    doc = pymupdf.open()
    page = doc.new_page(width=width_pt, height=height_pt)
    page.insert_image(page.rect, stream=buffer.getvalue())
    folder = args.get("out_dir") or str(Path(os.path.expanduser("~")) / "Documents")
    target = output_path(Path(folder) / "Scan.pdf", "", ".pdf", folder)
    doc.save(str(target), garbage=3, deflate=True)
    doc.close()
    return result([target], dpi=dpi, color=color)
