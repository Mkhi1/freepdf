"""HTML and URLs to PDF with headless Edge (Chromium) driven over the DevTools protocol."""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import psutil
from websocket import create_connection

from ..core import Job, ToolError, output_path, result
from ..registry import tool

EDGE_PATHS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)
INCH_PAGES = {"a4": (8.2677, 11.6929), "letter": (8.5, 11.0), "legal": (8.5, 14.0), "a3": (11.6929, 16.5354)}
MARGINS_IN = {"none": 0.0, "small": 0.4, "big": 0.9}
MAX_PAGE_INCHES = 200.0
BELOW_NORMAL = 0x00004000
NO_WINDOW = 0x08000000
PAGE_TIMEOUT = 60.0


def find_edge() -> str:
    for path in EDGE_PATHS:
        if Path(path).is_file():
            return path
    raise ToolError("missing_resource", "Microsoft Edge was not found, so web pages can't be converted to PDF.")


def resolve_source(source: str) -> str:
    text = str(source).strip()
    if not text:
        raise ToolError("bad_args", "Enter a web address or choose an HTML file.")
    parsed = urlparse(text)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return text
    if parsed.scheme == "file":
        local = Path(url2pathname(unquote(parsed.path)))
    elif len(parsed.scheme) <= 1:
        local = Path(text)
    else:
        raise ToolError("bad_args", "Only http and https addresses and local HTML files are supported.")
    if not local.is_file():
        raise ToolError("file_not_found", f"Could not find {local.name or text}. It may have been moved or deleted.")
    return local.resolve().as_uri()


def _launch(profile: str) -> tuple[subprocess.Popen, str]:
    args = [find_edge(), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--disable-background-networking", "--mute-audio", "--hide-scrollbars",
            "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                            creationflags=BELOW_NORMAL | NO_WINDOW)
    port_file = Path(profile) / "DevToolsActivePort"
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            parts = port_file.read_text().split() if port_file.exists() else []
        except OSError:
            parts = []  # Edge is still writing the file
        if len(parts) >= 2:
            return proc, f"ws://127.0.0.1:{parts[0]}{parts[1]}"
        time.sleep(0.1)
    _kill(proc, profile)
    raise ToolError("tool_failed", "Edge did not start. Close other Edge update windows and try again.")


def _kill(proc: subprocess.Popen, profile: str) -> None:
    """Stops every Edge using our private profile. The process we started may already have handed off to another."""
    try:
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.Error:
        pass
    for candidate in psutil.process_iter(["name", "cmdline"]):
        name = (candidate.info["name"] or "").lower()
        if name == "msedge.exe" and profile in " ".join(candidate.info["cmdline"] or []):
            try:
                candidate.kill()
            except psutil.Error:
                pass


class Cdp:
    def __init__(self, url: str):
        self.ws = create_connection(url, timeout=PAGE_TIMEOUT, suppress_origin=True)
        self.next_id = 0
        self.events: list[dict] = []

    def call(self, method: str, params: dict | None = None, session: str | None = None) -> dict:
        self.next_id += 1
        message = {"id": self.next_id, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        self.ws.send(json.dumps(message))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get("id") == self.next_id:
                if "error" in reply:
                    raise ToolError("tool_failed", f"Edge refused the request: {reply['error'].get('message', '')}")
                return reply.get("result", {})
            self.events.append(reply)

    def wait_event(self, name: str, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if any(e.get("method") == name for e in self.events):
                return True
            self.ws.settimeout(max(0.1, deadline - time.time()))
            try:
                self.events.append(json.loads(self.ws.recv()))
            except Exception:
                return False
        return False

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def _margin_inches(args: dict) -> float:
    margin = str(args.get("margin", "small")).lower()
    if margin not in MARGINS_IN:
        raise ToolError("bad_args", "Margin must be none, small or big.")
    return MARGINS_IN[margin]


def _print_params(args: dict, content_height_px: float) -> dict:
    margin = _margin_inches(args)
    size = str(args.get("page_size", "a4")).lower()
    if size not in INCH_PAGES:
        raise ToolError("bad_args", "Page size must be a4, a3, letter or legal.")
    width, height = INCH_PAGES[size]
    if str(args.get("orientation", "portrait")).lower() == "landscape":
        width, height = height, width
    base = {"printBackground": True, "preferCSSPageSize": False, "displayHeaderFooter": False,
            "marginLeft": margin, "marginRight": margin, "marginTop": margin, "marginBottom": margin}
    if args.get("one_long_page"):
        tall = min(MAX_PAGE_INCHES, content_height_px / 96.0 + 2 * margin + 0.05)
        return {**base, "paperWidth": width, "paperHeight": max(tall, 1.0), "pageRanges": "1"}
    return {**base, "paperWidth": width, "paperHeight": height}


def _render(cdp: Cdp, url: str, args: dict) -> bytes:
    target = cdp.call("Target.createTarget", {"url": "about:blank"})["targetId"]
    session = cdp.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
    cdp.call("Page.enable", session=session)
    nav = cdp.call("Page.navigate", {"url": url}, session)
    if nav.get("errorText"):
        raise ToolError("tool_failed", f"The page could not be loaded ({nav['errorText'].replace('net::', '')}). Check the address and your connection.")
    cdp.wait_event("Page.loadEventFired", PAGE_TIMEOUT)
    time.sleep(0.4)
    measure = "Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)"
    height = cdp.call("Runtime.evaluate", {"expression": measure, "returnByValue": True}, session)["result"].get("value", 0)
    pdf = cdp.call("Page.printToPDF", _print_params(args, float(height)), session)
    return base64.b64decode(pdf["data"])


def _name_for(resolved: str) -> Path:
    parsed = urlparse(resolved)
    if parsed.scheme == "file":
        return Path(url2pathname(unquote(parsed.path)))
    stem = (parsed.netloc + parsed.path).strip("/").replace("/", "-") or parsed.netloc
    return Path(stem[:60] + ".html")


def _fetch_pdf(job: Job, resolved: str, args: dict) -> bytes:
    profile = tempfile.mkdtemp(prefix="freepdf-edge-")
    proc = None
    cdp = None
    try:
        job.progress(0.1, "Starting the browser engine")
        proc, ws_url = _launch(profile)
        cdp = Cdp(ws_url)
        job.progress(0.3, "Loading the page")
        return _render(cdp, resolved, args)
    except ToolError:
        raise
    except Exception as err:
        raise ToolError("tool_failed", f"The page could not be converted: {err}")
    finally:
        if cdp:
            cdp.close()
        if proc:
            _kill(proc, profile)
        shutil.rmtree(profile, ignore_errors=True)


@tool("html_to_pdf")
def html_to_pdf(job: Job, args: dict) -> dict:
    resolved = resolve_source(args.get("source", ""))
    _margin_inches(args)
    data = _fetch_pdf(job, resolved, args)
    named = _name_for(resolved)
    local = urlparse(resolved).scheme == "file"
    out_dir = args.get("out_dir") or (str(named.parent) if local else str(Path(os.path.expanduser("~")) / "Documents"))
    target = output_path(named, "", ".pdf", out_dir)
    target.write_bytes(data)
    return result([target], source=resolved)
