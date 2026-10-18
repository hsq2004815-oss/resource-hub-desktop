"""Drive the running app's window for QA: close-to-tray, hotkey, visibility.

Phase 5 verification helper. Synthetic clicks are unreliable against Flutter, but
window messages and global key presses are not.

    python migration/tools/window_probe.py state
    python migration/tools/window_probe.py close          # WM_CLOSE -> hide to tray
    python migration/tools/window_probe.py keys "ctrl+space"
    python migration/tools/window_probe.py show           # WM_SYSCOMMAND restore

Exit code is non-zero when the window cannot be found.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes

PROCESS_NAME = "resource_hub.exe"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4 & 0xFFFFFFFFFFFFFFFF))
except Exception:
    user32.SetProcessDPIAware()

user32.EnumWindows.argtypes = [
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

WM_CLOSE = 0x0010

VK = {
    "ctrl": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "space": 0x20,
}
# F1..F24 => 0x70..0x87
for _n in range(1, 25):
    VK[f"f{_n}"] = 0x70 + _n - 1
# A..Z and 0..9
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK[_c] = ord(_c.upper())
for _d in "0123456789":
    VK[_d] = ord(_d)


def find_pids() -> set[int]:
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


def find_windows(pids: set[int]) -> list[tuple[int, bool, str]]:
    """Returns (hwnd, visible, title) for every top-level window of the process."""
    found: list[tuple[int, bool, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        found.append((hwnd, bool(user32.IsWindowVisible(hwnd)), buffer.value))
        return True

    user32.EnumWindows(callback, 0)
    return found


def press(combo: str) -> None:
    keys = [VK[part] for part in combo.lower().split("+") if part in VK]
    if not keys:
        raise SystemExit(f"unsupported combo: {combo}")
    for vk in keys:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
    for vk in reversed(keys):
        user32.keybd_event(vk, 0, 0x0002, 0)
        time.sleep(0.03)


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "state"
    pids = find_pids()
    if not pids:
        print(f"{PROCESS_NAME} is not running")
        return 1
    windows = find_windows(pids)
    if not windows:
        print(f"no top-level window for pid(s) {sorted(pids)}")
        return 1

    titled = [w for w in windows if w[2]]
    hwnd, visible, title = (titled or windows)[0]

    if action == "state":
        print(f"pid={sorted(pids)} hwnd={hwnd} visible={visible} title={title!r}")
        return 0

    if action == "close":
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        time.sleep(0.6)
        after = [w for w in find_windows(pids) if w[0] == hwnd]
        state = after[0][1] if after else None
        print(f"after WM_CLOSE: visible={state} process_alive={bool(find_pids())}")
        return 0

    if action == "keys":
        combo = sys.argv[2] if len(sys.argv) > 2 else "ctrl+space"
        press(combo)
        time.sleep(0.8)
        after = [w for w in find_windows(pids) if w[0] == hwnd]
        state = after[0][1] if after else None
        print(f"after {combo}: visible={state}")
        return 0

    print(f"unknown action: {action}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
