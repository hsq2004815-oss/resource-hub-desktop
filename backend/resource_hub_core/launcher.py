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

from .service import ServiceError

OPEN_FAILED_KEY = "open_folder_failed"

#: Indirection points so tests never spawn anything.
_open_url = webbrowser.open
_popen = subprocess.Popen
_startfile = getattr(os, "startfile", None)


def open_link(url: str) -> None:
    """Open a URL in the default browser. The legacy app ignored the result."""
    if not url:
        raise ServiceError(OPEN_FAILED_KEY, "empty url")
    _open_url(url)


def open_path(path: str) -> None:
    """Open a file or folder with its default handler."""
    if not path or not Path(path).exists():
        raise ServiceError(OPEN_FAILED_KEY, f"path does not exist: {path}")
    if _startfile is None:
        raise ServiceError(OPEN_FAILED_KEY, "os.startfile is Windows-only")
    _startfile(path)


def reveal_path(path: str) -> None:
    """Show the item selected in Explorer."""
    if not path or not Path(path).exists():
        raise ServiceError(OPEN_FAILED_KEY, f"path does not exist: {path}")
    _popen(["explorer", f"/select,{path}"])
