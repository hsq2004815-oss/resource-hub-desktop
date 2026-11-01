"""Launching external targets — the only place the backend touches the desktop.

Ported from ``open_selected`` / ``open_location_selected``
(``resource_hub.pyw:2698-2723``). Kept separate from :mod:`service` so the
business layer stays free of process side effects and remains testable.

The functions are module-level so tests can patch ``_startfile`` / ``_popen`` /
``_open_url`` instead of launching real windows.
"""

from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

from .browsers import Browser
from .openers import KIND_EDITOR, KIND_SYSTEM, Opener, find_opener
from .service import ServiceError

OPEN_FAILED_KEY = "open_folder_failed"

#: Indirection points so tests never spawn anything.
_open_url = webbrowser.open
_popen = subprocess.Popen
_startfile = getattr(os, "startfile", None)


def open_link(url: str, browser: Browser | None = None) -> None:
    """Open a URL, either in ``browser`` or in the system default browser."""
    if not url:
        raise ServiceError(OPEN_FAILED_KEY, "empty url")
    if browser is not None and browser.command:
        _popen([browser.command, url])
        return
    _open_url(url)


def open_path(path: str, opener_id: str = "") -> None:
    """Open a file or folder, optionally with one of the preset openers.

    An empty or unknown [opener_id] means the system default, so a stale value
    in the data file can never run something unexpected.
    """
    if not path or not Path(path).exists():
        raise ServiceError(OPEN_FAILED_KEY, f"path does not exist: {path}")
    opener = find_opener(opener_id)
    if opener is not None and opener.kind != KIND_SYSTEM:
        _open_with_opener(path, opener)
        return
    if _startfile is None:
        raise ServiceError(OPEN_FAILED_KEY, "os.startfile is Windows-only")
    _startfile(path)


def _child_env() -> dict[str, str]:
    """Environment for a launched program.

    ELECTRON_RUN_AS_NODE must go: when Drawer itself was started from a
    Node/Electron tool that sets it, an Electron editor we launch (VS Code,
    Cursor) runs as plain Node, treats the folder path as a script and dies
    with "Cannot find module ..." instead of opening a window.
    """
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    env.pop("ELECTRON_NO_ATTACH_CONSOLE", None)
    return env


def _open_with_opener(path: str, opener: Opener) -> None:
    """Start one of the preset programs on [path]."""
    target = Path(path)
    try:
        if opener.kind == KIND_EDITOR:
            _popen([opener.command, str(target)], env=_child_env())
            return
        # A terminal starts *in* the folder; for a file that means its parent.
        folder = target if target.is_dir() else target.parent
        if opener.id == "wt":
            _popen([opener.command, "-d", str(folder)], env=_child_env())
            return
        # Pass the working directory instead of typing "cd <path>": no quoting
        # rules to get wrong, and no way for a path to become a command.
        arguments = [opener.command]
        if opener.id == "cmd":
            arguments.append("/K")
        elif opener.id == "powershell":
            arguments.append("-NoExit")
        _popen(arguments, cwd=str(folder), env=_child_env())
    except OSError as exc:
        raise ServiceError(OPEN_FAILED_KEY, f"{opener.name}: {exc}") from exc


def reveal_path(path: str) -> None:
    """Show the item selected in Explorer."""
    if not path or not Path(path).exists():
        raise ServiceError(OPEN_FAILED_KEY, f"path does not exist: {path}")
    _popen(["explorer", f"/select,{path}"])
