import ctypes
import importlib
import json
import pkgutil
import queue
import sys
import threading
import traceback

from .core import Job, ToolError
from .registry import TOOLS

BELOW_NORMAL_PRIORITY_CLASS = 0x4000
VIEWER_MODULES = ("viewer",)
FAILED_MESSAGE = "This tool stopped on an unexpected problem. Try again, or try a different file."


def lower_priority() -> None:
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)


def tie_children_to_engine():
    """Windows stops Edge and Ghostscript with the engine, even if the app closes mid-conversion.

    Keep the returned handle alive: closing it is what ends the children.
    """
    if sys.platform != "win32":
        return None
    import win32api
    import win32job

    job = win32job.CreateJobObject(None, "")
    info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
    win32job.AssignProcessToJobObject(job, win32api.GetCurrentProcess())
    return job


def load_tools(only: tuple[str, ...] | None = None) -> None:
    from . import tools
    for module in pkgutil.iter_modules(tools.__path__):
        if only and module.name not in only:
            continue
        # One broken module must not take the other tools down with it.
        try:
            importlib.import_module(f"{tools.__name__}.{module.name}")
        except Exception:
            traceback.print_exc(file=sys.stderr)


def make_emitter(stream):
    lock = threading.Lock()

    def emit(message: dict) -> None:
        with lock:
            stream.write(json.dumps(message, ensure_ascii=False) + "\n")
            stream.flush()
    return emit


def run_job(request: dict, cancel_event: threading.Event, emit) -> None:
    job_id = request.get("id", "")
    job = Job(job_id, emit, cancel_event)
    try:
        fn = TOOLS.get(request.get("tool", ""))
        if fn is None:
            raise ToolError("unknown_tool", f"Unknown tool: {request.get('tool')}.")
        outcome = fn(job, request.get("args") or {})
        emit({"id": job_id, "type": "result", **outcome})
    except ToolError as err:
        emit({"id": job_id, "type": "error", "code": err.code, "message": err.message})
    except Exception:
        traceback.print_exc(file=sys.stderr)
        emit({"id": job_id, "type": "error", "code": "tool_failed", "message": FAILED_MESSAGE})


def worker(jobs: queue.Queue, cancels: dict, emit) -> None:
    while True:
        request = jobs.get()
        if request is None:
            return
        run_job(request, cancels[request["id"]], emit)
        cancels.pop(request["id"], None)


def read_requests(stream, jobs: queue.Queue, cancels: dict, emit) -> None:
    for line in stream:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            emit({"id": "", "type": "error", "code": "bad_args", "message": "Bad request."})
            continue
        if "cancel" in request:
            event = cancels.get(request["cancel"])
            if event:
                event.set()
            continue
        cancels[request.get("id", "")] = threading.Event()
        jobs.put({**request, "id": request.get("id", "")})


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    protocol_out = sys.stdout
    # Libraries such as pdf2docx print progress, which would corrupt the JSON stream.
    sys.stdout = sys.stderr
    lower_priority()
    role = sys.argv[1] if len(sys.argv) > 1 else "all"
    load_tools(VIEWER_MODULES if role == "viewer" else None)
    children_job = None if role == "viewer" else tie_children_to_engine()
    emit = make_emitter(protocol_out)
    jobs: queue.Queue = queue.Queue()
    cancels: dict[str, threading.Event] = {}
    # PyMuPDF is not thread safe, so all tools run on this one worker thread.
    thread = threading.Thread(target=worker, args=(jobs, cancels, emit), daemon=True)
    thread.start()
    read_requests(sys.stdin, jobs, cancels, emit)
    jobs.put(None)
    thread.join()
    del children_job


if __name__ == "__main__":
    main()
