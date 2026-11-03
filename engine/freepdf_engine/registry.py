from collections.abc import Callable

from . import __version__
from .core import Job

TOOLS: dict[str, Callable[[Job, dict], dict]] = {}


def tool(name: str):
    def register(fn):
        if name in TOOLS:
            raise ValueError(f"Tool registered twice: {name}")
        TOOLS[name] = fn
        return fn
    return register


@tool("ping")
def ping(job: Job, args: dict) -> dict:
    return {"outputs": [], "summary": {"version": __version__, "tools": sorted(TOOLS)}}
