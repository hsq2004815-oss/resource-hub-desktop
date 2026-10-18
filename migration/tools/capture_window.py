"""Capture the Resource Hub window to a PNG.

Used for Phase 2 visual verification. Finds the top-level visible window owned by
the `resource_hub` process, brings it to the foreground, and grabs its bounds.

    D:\\miniconda3\\python.exe migration/tools/capture_window.py [output.png]
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

PROCESS_NAME = "resource_hub.exe"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Must happen before ANY coordinate query. Without per-monitor-v2 awareness this
# process sees virtualized (logical) coordinates while ImageGrab captures physical
# pixels, so the grabbed region covers only part of the window at >100% DPI.
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4 & 0xFFFFFFFFFFFFFFFF))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        user32.SetProcessDPIAware()

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
]
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]

HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040


def find_pids() -> set[int]:
    """Return PIDs of every running resource_hub.exe via toolhelp-free WMI-less scan."""
    import subprocess

    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {PROCESS_NAME}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    ).stdout
    pids: set[int] = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == PROCESS_NAME.lower():
            try:
                pids.add(int(parts[1]))
            except ValueError:
                continue
    return pids


def find_window(pids: set[int]) -> int:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else 0


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "migration/screenshots/phase2-light.png"
    )
    pids = find_pids()
    if not pids:
        print(f"{PROCESS_NAME} is not running")
        return 1
    hwnd = find_window(pids)
    if not hwnd:
        print("no visible top-level window found")
        return 1

    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # Another app may own the foreground (and the screen area we are about to
    # grab), so pin our window on top for the duration of the capture.
    user32.SetWindowPos(
        hwnd, HWND_TOPMOST, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
    )
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    time.sleep(1.0)

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
    user32.SetWindowPos(
        hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    print(f"hwnd={hwnd} rect={rect.left},{rect.top} {width}x{height} saved={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
