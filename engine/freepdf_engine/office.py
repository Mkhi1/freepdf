"""Hidden Microsoft Office automation.

Every call creates its own private Office instance with DispatchEx, never
attaches to one the user has open, and always quits it. A watchdog kills the
instance if a modal prompt or a hang keeps it busy past the timeout.
"""
import sys
import threading
from collections.abc import Callable
from pathlib import Path

import psutil

from .core import ToolError

DEFAULT_TIMEOUT = 240.0
PROG_IDS = {"word": "Word.Application", "excel": "Excel.Application", "powerpoint": "PowerPoint.Application"}
_QUIT_APPS: list = []
NICE_NAMES = {"word": "Word", "excel": "Excel", "powerpoint": "PowerPoint"}


def _window_pid(app, kind: str) -> int | None:
    try:
        import win32process
        handle = app.HWND if kind == "powerpoint" else app.Hwnd
        return win32process.GetWindowThreadProcessId(handle)[1]
    except Exception:
        return None


def _kill_tree(pid: int | None) -> None:
    if not pid:
        return
    try:
        proc = psutil.Process(pid)
        for child in proc.children(recursive=True):
            child.kill()
        proc.kill()
    except psutil.Error:
        pass


def _configure(app, kind: str) -> None:
    if kind == "word":
        app.Visible = False
        app.DisplayAlerts = 0
        app.AutomationSecurity = 3  # msoAutomationSecurityForceDisable: no macros
    elif kind == "excel":
        app.Visible = False
        app.DisplayAlerts = False
        app.AutomationSecurity = 3
        app.AskToUpdateLinks = False
    else:
        app.DisplayAlerts = 1  # ppAlertsNone
        app.AutomationSecurity = 3


def _worker(kind: str, work: Callable, state: dict) -> None:
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = None
    try:
        app = win32com.client.DispatchEx(PROG_IDS[kind])
        state["pid"] = _window_pid(app, kind) if kind != "powerpoint" else None
        _configure(app, kind)
        state["value"] = work(app)
    except BaseException as err:
        state["error"] = err
    finally:
        _quit(app)
        if app is not None:
            _QUIT_APPS.append(app)  # releasing a proxy to an exited server raises a noisy RPC error; keep it alive
        state["done"].set()


def _quit(app) -> None:
    if app is None:
        return
    try:
        app.Quit()
    except Exception:
        pass


def _missing(err: BaseException) -> bool:
    text = str(err)
    return "Invalid class string" in text or "-2147221005" in text or "-2147221164" in text


def run_office(kind: str, work: Callable, timeout: float = DEFAULT_TIMEOUT, cancelled: Callable[[], bool] | None = None):
    """Run work(app) against a private hidden Office instance and return its value."""
    if sys.platform != "win32":
        raise ToolError("office_missing", "Microsoft Office is only available on Windows.")
    name = NICE_NAMES[kind]
    state = {"done": threading.Event()}
    thread = threading.Thread(target=_worker, args=(kind, work, state), daemon=True)
    before = _office_pids(kind)
    thread.start()
    waited = 0.0
    while not state["done"].wait(0.25):
        waited += 0.25
        if cancelled and cancelled():
            _abort(kind, state, before)
            raise ToolError("cancelled", "Stopped.")
        if waited >= timeout:
            _abort(kind, state, before)
            raise ToolError("office_failed", f"{name} did not finish within {int(timeout)} seconds. "
                            "The file may be very large, damaged or waiting for a prompt. Try again or use a simpler file.")
    return _outcome(state, name)


def _outcome(state: dict, name: str):
    err = state.get("error")
    if err is None:
        return state.get("value")
    if isinstance(err, ToolError):
        raise err
    if _missing(err):
        raise ToolError("office_missing", f"{name} is not installed, so this conversion is not available.")
    raise ToolError("office_failed", f"{name} could not convert this file: {_short(err)}")


def _short(err: BaseException) -> str:
    details = getattr(err, "excepinfo", None)
    if details and len(details) > 2 and details[2]:
        return str(details[2]).strip()
    return str(err).strip().splitlines()[0][:200] if str(err).strip() else type(err).__name__


def _office_pids(kind: str) -> set[int]:
    exe = {"word": "winword.exe", "excel": "excel.exe", "powerpoint": "powerpnt.exe"}[kind]
    return {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == exe}


def _abort(kind: str, state: dict, before: set[int]) -> None:
    pids = {state.get("pid")} - {None}
    if not pids:
        pids = _office_pids(kind) - before  # only processes this call started
    for pid in pids:
        _kill_tree(pid)
    state["done"].wait(5)


def check_office(kind: str) -> None:
    import winreg
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, PROG_IDS[kind]))
    except OSError:
        raise ToolError("office_missing", f"{NICE_NAMES[kind]} is not installed, so this conversion is not available.")


def win_path(path: str | Path) -> str:
    return str(Path(path).resolve())
