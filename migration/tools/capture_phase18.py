"""Capture Phase 18 screenshots from the running stable build.

Simulates one extension /ping so the settings dialog shows "已连接", then grabs:
- phase18-settings-extension.png (bookmark section: delete mode, extension state)
- phase18-delete-dialog.png (delete confirm with the browser checkbox)

The dialog is cancelled with Esc, so no resource or bookmark is changed.
"""

from __future__ import annotations

import ctypes
import json
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

REPO_ROOT = Path(__file__).resolve().parents[2]
SHOTS = REPO_ROOT / "migration" / "screenshots"
EXE = (
    REPO_ROOT
    / "release"
    / "ResourceHub-Desktop-20261017-1835"
    / "resource_hub.exe"
)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4 & 0xFFFFFFFFFFFFFFFF))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        user32.SetProcessDPIAware()

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.EnumWindows.argtypes = [
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
]
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def find_window(executable: Path) -> int:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if not handle:
            return True
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ) and Path(buffer.value).resolve() == executable.resolve():
                found.append(hwnd)
                return False
        finally:
            kernel32.CloseHandle(handle)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else 0


def force_foreground(hwnd: int) -> None:
    swp = 0x0002 | 0x0001
    user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, swp)
    user32.SetWindowPos(hwnd, wintypes.HWND(-2), 0, 0, 0, 0, swp)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)


def click_at(x: int, y: int, pause: float = 0.7) -> None:
    user32.SetCursorPos(x, y)
    time.sleep(0.12)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.03)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(pause)


def press_escape() -> None:
    user32.keybd_event(0x1B, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(0x1B, 0, 0, 0x0002)
    time.sleep(0.5)


def capture(hwnd: int, name: str) -> Path:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    target = SHOTS / name
    image = ImageGrab.grab(
        bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    print("captured", target)
    return target


def ping_extension() -> None:
    for port in range(47821, 47831):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/ping", timeout=0.4
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
                if body.get("app") == "resource-hub":
                    print("extension ping ok on", port)
                    return
        except Exception:
            continue
    raise SystemExit("bridge not reachable; is the app running?")


def main() -> int:
    hwnd = find_window(EXE)
    if hwnd == 0:
        return 1
    force_foreground(hwnd)
    ping_extension()
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top

    # Settings dialog with the extension connected.
    click_at(
        rect.left + int(width * 0.956),
        rect.top + int(height * 0.125),
        pause=1.2,
    )
    # Scroll to the bookmark section (delete mode + extension state).
    user32.SetCursorPos(
        rect.left + int(width * 0.5), rect.top + int(height * 0.6)
    )
    time.sleep(0.2)
    for _ in range(8):
        user32.mouse_event(0x0800, 0, 0, -120, 0)
        time.sleep(0.12)
    time.sleep(0.6)
    capture(hwnd, "phase18-settings-extension.png")
    press_escape()

    # Sites list: switch mode, clear any leftover filter, then select row 1.
    click_at(rect.left + int(width * 0.753), rect.top + int(height * 0.080))
    time.sleep(0.8)
    # "显示全部" reset link sits in the middle of the empty state if a stale
    # filter is active; harmless when the list is already visible.
    click_at(rect.left + int(width * 0.501), rect.top + int(height * 0.617))
    time.sleep(0.6)
    capture(hwnd, "phase18-sites-list.png")
    click_at(rect.left + int(width * 0.247), rect.top + int(height * 0.233))
    click_at(
        rect.left + int(width * 0.901),
        rect.top + int(height * 0.125),
        pause=1.0,
    )
    capture(hwnd, "phase18-delete-dialog.png")
    press_escape()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
