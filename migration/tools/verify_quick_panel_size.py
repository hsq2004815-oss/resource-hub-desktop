"""Phase 24 QA: the quick panel must stay a small 480x600 HUD even when the
main window is maximized (or gets maximized afterwards).

Regression guarded here: EnterQuickMode used to skip IsZoomed(), so opening the
HUD from a maximized window produced a full-size panel (SetWindowPos sizing is
ignored while a window is maximized). The fix restores the window first and
puts the maximized state back when the HUD closes.

Run with a release build available (the script copies it to a temp folder and
seeds demo data; the stable install is restarted at the end):

    D:\\miniconda3\\python.exe migration/tools/verify_quick_panel_size.py `
        --build release\\ResourceHub-Desktop-20261019-0650
"""

from __future__ import annotations

import argparse
import ctypes
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import capture_usage_shots as shots  # noqa: E402

user32 = ctypes.windll.user32
USER32 = user32
USER32.GetDpiForWindow.argtypes = [wintypes.HWND]
USER32.GetDpiForWindow.restype = wintypes.UINT
USER32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]

SW_MAXIMIZE = 3
SW_RESTORE = 9
GWL_STYLE = -16
WS_MAXIMIZE = 0x01000000
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080

STABLE = shots.REPO_ROOT / "release" / "ResourceHub-Desktop-20261017-1835"

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def window_size(hwnd: int) -> tuple[int, int]:
    left, top, right, bottom = shots.window_rect(hwnd)
    return right - left, bottom - top


def maximized(hwnd: int) -> bool:
    return bool(user32.GetWindowLongPtrW(hwnd, GWL_STYLE) & WS_MAXIMIZE)


def toolwindow(hwnd: int) -> bool:
    return bool(user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW)


def expected_hud_size(hwnd: int) -> tuple[int, int]:
    dpi = USER32.GetDpiForWindow(hwnd) or 96
    return (
        int(round(480 * dpi / 96)),
        int(round(600 * dpi / 96)),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", required=True, type=Path)
    args = parser.parse_args()
    build = args.build.resolve()

    shots.kill_app()
    work = Path(tempfile.mkdtemp(prefix="rh-hud-size-qa-"))
    process = None
    try:
        qa_dir = work / "app"
        shutil.copytree(build, qa_dir)
        shots.seed(qa_dir)
        process = subprocess.Popen([str(qa_dir / "resource_hub.exe")], cwd=str(qa_dir))

        hwnd = 0
        deadline = time.time() + 30
        while time.time() < deadline:
            if process.poll() is not None:
                print("app exited during startup")
                return 1
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq resource_hub.exe", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, encoding="utf-8", errors="ignore",
            ).stdout
            pid = None
            for line in out.splitlines():
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) >= 2 and parts[0].lower() == "resource_hub.exe":
                    try:
                        pid = int(parts[1])
                    except ValueError:
                        pid = None
                    break
            if pid:
                hwnd = shots.find_window(pid)
                if hwnd:
                    width, height = window_size(hwnd)
                    if width > 800 and height > 600:
                        break
            time.sleep(0.2)
        if not hwnd:
            print("no main window")
            return 1
        shots.force_foreground(hwnd)
        for _ in range(60):
            if shots.list_loaded(hwnd):
                break
            time.sleep(0.25)
        expected = expected_hud_size(hwnd)
        print(f"  expected HUD size: {expected[0]}x{expected[1]}")

        def open_hud() -> tuple[int, int]:
            shots.key_combo(["ctrl", "alt", "shift", "f"])
            time.sleep(1.2)
            return window_size(hwnd)

        def close_hud() -> None:
            shots.key_combo(["ctrl", "alt", "shift", "f"])
            time.sleep(1.0)

        # 1. Normal window -> small HUD -> close restores the normal window.
        normal_size = window_size(hwnd)
        size = open_hud()
        record("hud_from_normal_is_small", size == expected and toolwindow(hwnd),
               f"{size[0]}x{size[1]} toolwindow={toolwindow(hwnd)}")
        close_hud()
        record("close_restores_normal_window", window_size(hwnd) == normal_size,
               f"{window_size(hwnd)[0]}x{window_size(hwnd)[1]}")

        # 2. Maximized window -> small HUD -> close restores the maximized state.
        USER32.ShowWindow(hwnd, SW_MAXIMIZE)
        time.sleep(0.8)
        maximized_before = maximized(hwnd)
        size = open_hud()
        record("hud_from_maximized_is_small", size == expected,
               f"{size[0]}x{size[1]} (was maximized={maximized_before})")
        close_hud()
        record("close_from_hud_restores_maximized",
               maximized(hwnd), f"maximized={maximized(hwnd)}")

        # 3. Repeated open/close while maximized stays deterministic.
        size = open_hud()
        record("second_hud_from_maximized_is_small", size == expected,
               f"{size[0]}x{size[1]}")
        close_hud()
        record("second_close_restores_maximized", maximized(hwnd),
               f"maximized={maximized(hwnd)}")

        failed = [name for name, ok, _ in results if not ok]
        print(f"\n{len(results) - len(failed)}/{len(results)} passed")
        if failed:
            print("failed:", ", ".join(failed))
        return 0 if not failed else 1
    finally:
        if process is not None and process.poll() is None:
            process.kill()
        shots.kill_app()
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(shots.DEMO_ROOT, ignore_errors=True)
        if (STABLE / "resource_hub.exe").exists():
            subprocess.Popen([str(STABLE / "resource_hub.exe")], cwd=str(STABLE))
            print("  stable app restarted")


if __name__ == "__main__":
    sys.exit(main())
