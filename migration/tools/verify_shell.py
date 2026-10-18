"""End-to-end shell QA for the Flutter client (Phase 5b).

Checks the parts that only exist on a real desktop and cannot be unit-tested:

  1. close button hides to tray, process stays alive
  2. the global hotkey (owned by the Python backend) brings the window back
  3. a second launch wakes the existing window instead of starting a new process
  4. WM_DROPFILES from Explorer adds the dropped folders to folders.json

Synthetic *clicks* are unreliable against Flutter on this machine (see
MEMORY.md), so this drives window messages and real key presses instead of the
mouse. Run from the repository root, with the release build already present:

    D:\\miniconda3\\python.exe migration\\tools\\verify_shell.py
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "app" / "build" / "windows" / "x64" / "runner" / "Release" / "resource_hub.exe"
SCREENSHOT_DIR = ROOT / "migration" / "screenshots"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4 & 0xFFFFFFFFFFFFFFFF))
except Exception:
    user32.SetProcessDPIAware()

user32.EnumWindows.argtypes = [
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

WM_CLOSE = 0x0010
WM_DROPFILES = 0x0233
GMEM_MOVEABLE = 0x0002

VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10}
for _n in range(1, 25):
    VK[f"f{_n}"] = 0x70 + _n - 1
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK[_c] = ord(_c.upper())
VK["space"] = 0x20

PROCESS_NAME = "resource_hub.exe"
HOTKEY = "ctrl+alt+shift+f12"


class DROPFILES(ctypes.Structure):
    _fields_ = [
        ("pFiles", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("fNC", wintypes.BOOL),
        ("fWide", wintypes.BOOL),
    ]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def check(condition: bool, message: str) -> None:
    print(f"{'PASS' if condition else 'FAIL'}: {message}")
    if not condition:
        raise SystemExit(1)


def pids() -> set[int]:
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {PROCESS_NAME}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    ).stdout
    found: set[int] = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == PROCESS_NAME.lower():
            try:
                found.add(int(parts[1]))
            except ValueError:
                continue
    return found


def windows() -> list[tuple[int, bool, str, int]]:
    result: list[tuple[int, bool, str, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if buffer.value and user32.IsWindowVisible(hwnd):
            result.append((hwnd, True, buffer.value, pid.value))
        elif buffer.value:
            result.append((hwnd, False, buffer.value, pid.value))
        return True

    user32.EnumWindows(callback, 0)
    return result


def find_main_window(timeout: float = 25.0) -> tuple[int, int]:
    """Waits until a *visible* top-level window of the app exists."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        live = pids()
        for hwnd, visible, _title, pid in windows():
            if pid in live and visible:
                return hwnd, pid
        time.sleep(0.3)
    fail("main window never became visible")


def is_visible(hwnd: int) -> bool:
    return bool(user32.IsWindowVisible(hwnd))


def child_window(top_hwnd: int) -> int:
    """The Flutter view window: real Explorer drops land here, not on the frame.

    Regression for the drag & drop bug where only `WM_DROPFILES` sent to the
    top-level window worked, so dragging a folder onto the app did nothing.
    """
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    child = user32.GetWindow(top_hwnd, 5)  # GW_CHILD
    return child if child else top_hwnd


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


def drop_paths(hwnd: int, paths: list[str]) -> None:
    encoded = b""
    for path in paths:
        encoded += path.encode("utf-16-le") + b"\x00\x00"
    encoded += b"\x00\x00"

    header_size = ctypes.sizeof(DROPFILES)
    total = header_size + len(encoded)
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, total)
    if not handle:
        fail("GlobalAlloc failed")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        fail("GlobalLock failed")
    try:
        header = DROPFILES()
        header.pFiles = header_size
        header.fNC = False
        header.fWide = True
        ctypes.memmove(pointer, ctypes.byref(header), header_size)
        ctypes.memmove(pointer + header_size, encoded, len(encoded))
    finally:
        kernel32.GlobalUnlock(handle)
    user32.PostMessageW(hwnd, WM_DROPFILES, handle, 0)


def read_folders(data_dir: Path) -> list[dict]:
    path = data_dir / "folders.json"
    for _ in range(50):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        time.sleep(0.1)
    return []


def screenshot(name: str) -> None:
    target = SCREENSHOT_DIR / name
    subprocess.run(
        [sys.executable, str(ROOT / "migration" / "tools" / "capture_window.py"), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    print(f"      screenshot: {target.relative_to(ROOT)}")


def main() -> int:
    if not EXE.exists():
        fail(f"release build missing: {EXE}")

    subprocess.run(["taskkill", "/IM", PROCESS_NAME, "/F"], capture_output=True)

    temp = Path(tempfile.mkdtemp(prefix="rh-shell-"))
    print(f"data dir: {temp}")
    for name in ("sites.json", "folders.json"):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, temp / name)
    (temp / "settings.json").write_text(
        json.dumps(
            {
                "language": "zh",
                "globalHotkeyEnabled": True,
                "globalHotkeyId": "Ctrl + Alt + Shift + F12",
                "launchAtStartup": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    drop_a = temp / "拖入的文件夹 A"
    drop_b = temp / "dropped-b"
    drop_a.mkdir()
    drop_b.mkdir()

    env = dict(os.environ)
    env["RH_DATA_DIR"] = str(temp)

    # 1. launch -------------------------------------------------------------
    process = subprocess.Popen([str(EXE)], cwd=str(ROOT), env=env)
    hwnd, pid = find_main_window()
    title = next((t for h, v, t, p in windows() if h == hwnd), "")
    print(f"      pid={pid} hwnd={hwnd} title={title!r}")
    time.sleep(1.0)
    check(is_visible(hwnd), "window visible after launch")
    screenshot("phase5b-shell-start.png")

    # 2. close -> tray ------------------------------------------------------
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    time.sleep(0.8)
    check(not is_visible(hwnd), "WM_CLOSE hides the window")
    check(process.poll() is None and pid in pids(), "process stays alive in the tray")

    # 3. hotkey -> show -----------------------------------------------------
    press(HOTKEY)
    time.sleep(1.0)
    check(is_visible(hwnd), f"global hotkey {HOTKEY} shows the window")

    # 4. second launch wakes, does not duplicate ----------------------------
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    time.sleep(0.6)
    second = subprocess.Popen([str(EXE)], cwd=str(ROOT), env=env)
    second.wait(timeout=15)
    time.sleep(1.0)
    check(len(pids()) == 1, "second launch does not leave a second process")
    check(is_visible(hwnd), "second launch wakes the existing window")

    # 5. drag & drop --------------------------------------------------------
    before = {item.get("path") for item in read_folders(temp)}
    target = child_window(hwnd)
    print(f"      drop target hwnd={target} (Flutter view child of {hwnd})")
    drop_paths(target, [str(drop_a), str(drop_b)])
    time.sleep(1.5)
    after = read_folders(temp)
    dropped = [item for item in after if item.get("path") in {str(drop_a), str(drop_b)}]
    check(len(dropped) >= 2, f"WM_DROPFILES added {len(dropped)} folders to folders.json")
    check(len(after) == len(before) + 2, "folders.json grew by exactly the dropped entries")
    screenshot("phase5b-shell-drop.png")

    # 6. shutdown via tray-equivalent quit ----------------------------------
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
    print("PASS: shell QA complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
