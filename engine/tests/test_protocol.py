import json
import subprocess
import sys
import time
from pathlib import Path

import psutil

ENGINE_ROOT = Path(__file__).resolve().parent.parent


ALL_TOOLS = {
    "merge", "split", "organize", "rotate", "crop", "compress", "repair", "pdfa", "ocr", "protect", "unlock",
    "info", "thumb", "page_text", "search", "word_to_pdf", "ppt_to_pdf", "excel_to_pdf", "images_to_pdf",
    "html_to_pdf", "scan_to_pdf", "list_scanners", "pdf_to_word", "pdf_to_ppt", "pdf_to_excel", "pdf_to_images",
    "pdf_to_text", "edit", "annotate", "page_numbers", "watermark", "sign", "make_signature", "redact",
    "compare", "translate", "summarize", "ping",
}
VIEWER_TOOLS = {"info", "thumb", "page_text", "search", "ping"}


def call_engine(*requests: dict, role: tuple[str, ...] = ()) -> list[dict]:
    lines = "".join(json.dumps(r) + "\n" for r in requests)
    done = subprocess.run(
        [sys.executable, "-m", "freepdf_engine", *role],
        cwd=ENGINE_ROOT, input=lines.encode("utf-8"), capture_output=True, timeout=60,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return [json.loads(line) for line in done.stdout.decode("utf-8").splitlines()]


def test_ping_answers_with_version_and_tools():
    [reply] = call_engine({"id": "1", "tool": "ping"})
    assert reply["type"] == "result"
    assert "ping" in reply["summary"]["tools"]


def test_every_tool_is_registered():
    [reply] = call_engine({"id": "1", "tool": "ping"})
    assert set(reply["summary"]["tools"]) == ALL_TOOLS


def test_viewer_role_loads_only_the_viewer_tools():
    [reply] = call_engine({"id": "1", "tool": "ping"}, role=("viewer",))
    assert set(reply["summary"]["tools"]) == VIEWER_TOOLS


def test_unused_layout_model_is_not_loaded():
    code = "import sys, freepdf_engine, pymupdf; print('onnxruntime' in sys.modules)"
    done = subprocess.run([sys.executable, "-c", code], cwd=ENGINE_ROOT, capture_output=True, timeout=60)
    assert done.stdout.decode().strip() == "False"


def test_helpers_stop_when_the_engine_is_killed():
    parent_code = (
        "import subprocess, sys, time\n"
        "from freepdf_engine.__main__ import tie_children_to_engine\n"
        "job = tie_children_to_engine()\n"
        "child = subprocess.Popen(['ping', '-n', '60', '127.0.0.1'], stdout=subprocess.DEVNULL, creationflags=0x08000000)\n"
        "print(child.pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    parent = subprocess.Popen([sys.executable, "-c", parent_code], cwd=ENGINE_ROOT, stdout=subprocess.PIPE)
    child_pid = int(parent.stdout.readline())
    assert psutil.pid_exists(child_pid)
    parent.kill()
    parent.wait(timeout=10)
    deadline = time.time() + 5
    while psutil.pid_exists(child_pid) and time.time() < deadline:
        time.sleep(0.1)
    assert not psutil.pid_exists(child_pid), "the helper must not outlive the engine"


def test_unknown_tool_is_a_clean_error():
    [reply] = call_engine({"id": "2", "tool": "nope"})
    assert reply == {"id": "2", "type": "error", "code": "unknown_tool", "message": "Unknown tool: nope."}


def test_requests_answer_in_order():
    replies = call_engine({"id": "a", "tool": "ping"}, {"id": "b", "tool": "ping"})
    assert [r["id"] for r in replies] == ["a", "b"]
