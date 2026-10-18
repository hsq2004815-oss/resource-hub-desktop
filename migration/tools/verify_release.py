"""Clean-room check for the packaged release folder (Phase 6).

Copies the release folder to a fresh temporary directory (so nothing resolves
back to the repository), launches it without any RH_* environment variables and
verifies that:

  1. the window shows up,
  2. the bundled `backend\\resource_hub_backend.exe` is what gets spawned
     (no system Python involved),
  3. first run seeds sites.json / folders.json next to the executable,
  4. the shell still talks to the backend (the list renders real data).

    D:\\miniconda3\\python.exe migration\\tools\\verify_release.py
    D:\\miniconda3\\python.exe migration\\tools\\verify_release.py --keep
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
EXE_NAME = "resource_hub.exe"
BACKEND_NAME = "resource_hub_backend.exe"
SCREENSHOT = ROOT / "migration" / "screenshots" / "phase6-release-clean.png"

user32 = ctypes.windll.user32
user32.EnumWindows.argtypes = [
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4 & 0xFFFFFFFFFFFFFFFF))
except Exception:
    user32.SetProcessDPIAware()


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def check(condition: bool, message: str) -> None:
    print(f"{'PASS' if condition else 'FAIL'}: {message}")
    if not condition:
        raise SystemExit(1)


def latest_release() -> Path:
    candidates = sorted((ROOT / "release").glob("ResourceHub-Desktop-*"))
    if not candidates:
        fail("no release bundle found; run build-flutter-release.ps1 first")
    return candidates[-1]


def pids(name: str) -> set[int]:
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    ).stdout
    found: set[int] = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            try:
                found.add(int(parts[1]))
            except ValueError:
                continue
    return found


def visible_window(pid: int, timeout: float = 25.0) -> int | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        found: list[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if (
                owner.value == pid
                and user32.IsWindowVisible(hwnd)
                and user32.GetWindowTextLengthW(hwnd) > 0
            ):
                found.append(hwnd)
            return True

        user32.EnumWindows(callback, 0)
        if found:
            return found[0]
        time.sleep(0.3)
    return None


def child_processes(pid: int) -> list[tuple[int, str]]:
    """Direct children of [pid] via the Toolhelp snapshot (wmic is gone on Win11)."""
    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    ]
    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    ]

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return []
    result: list[tuple[int, str]] = []
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    try:
        if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                if entry.th32ParentProcessID == pid:
                    result.append((entry.th32ProcessID, entry.szExeFile))
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)
    return result


def main() -> int:
    keep = "--keep" in sys.argv
    source = latest_release()
    print(f"release: {source}")

    work = Path(tempfile.mkdtemp(prefix="rh-release-"))
    installed = work / source.name
    print(f"clean room: {installed}")
    shutil.copytree(source, installed)

    for name in ("sites.json", "folders.json", "settings.json"):
        if (installed / name).exists():
            fail(f"release bundle should not ship {name}")

    env = {k: v for k, v in os.environ.items() if not k.startswith("RH_")}
    process = subprocess.Popen([str(installed / EXE_NAME)], cwd=str(installed), env=env)

    try:
        hwnd = visible_window(process.pid)
        check(hwnd is not None, "window appears in the clean room")
        time.sleep(1.5)

        children = child_processes(process.pid)
        names = {name.lower() for _pid, name in children}
        check(
            BACKEND_NAME.lower() in names,
            f"bundled backend is the child process ({sorted(names)})",
        )
        check(
            "python.exe" not in names,
            "no system Python is involved (frozen backend only)",
        )

        sites = installed / "sites.json"
        folders = installed / "folders.json"
        check(sites.exists(), "first run seeds sites.json next to the exe")
        check(folders.exists(), "first run seeds folders.json next to the exe")
        seeded = json.loads(sites.read_text(encoding="utf-8"))
        check(
            len(seeded) == 2,
            f"sample sites contain 2 entries (got {len(seeded)})",
        )

        subprocess.run(
            [
                sys.executable,
                str(ROOT / "migration" / "tools" / "capture_window.py"),
                str(SCREENSHOT),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        print(f"      screenshot: {SCREENSHOT.relative_to(ROOT)}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"kept clean room at {installed}")

    print("PASS: packaged release verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
