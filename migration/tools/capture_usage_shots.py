"""Capture clean screenshots of 抽屉 for the user guide (docs/images/).

Runs a throw-away copy of a release build with seeded, non-personal data so the
document does not expose the owner's real folders/paths. The shipped app and its
data are never touched; the stable app is expected to be closed by the caller or
is killed/restarted there.

Usage:
    python migration/tools/capture_usage_shots.py --build release\\ResourceHub-Desktop-20261018-2215
"""

from __future__ import annotations

import argparse
import ctypes
import json
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np
from PIL import ImageGrab

REPO_ROOT = Path(__file__).resolve().parents[2]
SHOTS = REPO_ROOT / "docs" / "images"
PROCESS_NAME = "resource_hub.exe"

ROW_CLICK = (0.151, 0.234)
SETTINGS_GEAR = (0.954, 0.122)
DEMO_ROOT = Path(r"D:\DrawerDemo")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4 & 0xFFFFFFFFFFFFFFFF))
except Exception:  # pragma: no cover
    user32.SetProcessDPIAware()

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
VK = {
    "ctrl": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "esc": 0x1B,
    "f": 0x46,
    "l": 0x4C,
    "space": 0x20,
}


def kill_app() -> None:
    subprocess.run(
        ["taskkill", "/IM", PROCESS_NAME, "/F"],
        capture_output=True,
        text=True,
        errors="ignore",
    )
    time.sleep(1.2)


def find_window(pid: int) -> int:
    candidates: list[tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid:
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            area = (rect.right - rect.left) * (rect.bottom - rect.top)
            candidates.append((area, hwnd))
        return True

    user32.EnumWindows(callback, 0)
    candidates.sort(reverse=True)
    return candidates[0][1] if candidates else 0


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def force_foreground(hwnd: int) -> None:
    user32.ShowWindow(hwnd, 9)
    user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x0002 | 0x0001)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)


def click_at(x: float, y: float) -> None:
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.45)


def move_neutral(hwnd: int) -> None:
    left, top, _, _ = window_rect(hwnd)
    user32.SetCursorPos(int(left + 8), int(top + 8))
    time.sleep(0.45)


def key_combo(keys: list[str]) -> None:
    pressed: list[int] = []
    try:
        for name in keys:
            vk = VK[name]
            user32.keybd_event(vk, 0, 0, 0)
            pressed.append(vk)
            time.sleep(0.03)
        for vk in reversed(pressed):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.03)
    finally:
        for vk in reversed(pressed):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.2)


def tap_escape() -> None:
    user32.keybd_event(VK["esc"], 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK["esc"], 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.5)


def capture(hwnd: int, name: str, crop: tuple[float, float, float, float] | None = None) -> Path:
    left, top, right, bottom = window_rect(hwnd)
    image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    if crop is not None:
        x0, y0, x1, y1 = crop
        image = image.crop(
            (
                int(image.width * x0),
                int(image.height * y0),
                int(image.width * x1),
                int(image.height * y1),
            )
        )
    target = SHOTS / name
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    print(f"  -> {name} {image.width}x{image.height}")
    return target


def list_loaded(hwnd: int) -> bool:
    left, top, right, bottom = window_rect(hwnd)
    width, height = right - left, bottom - top
    image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    crop = image.crop(
        (
            int(width * 0.10),
            int(height * 0.18),
            int(width * 0.55),
            int(height * 0.38),
        )
    )
    gray = np.asarray(crop.convert("L"))
    return int((gray < 140).sum()) > 300


def seed(qa_dir: Path) -> None:
    shutil.rmtree(DEMO_ROOT, ignore_errors=True)
    tree = DEMO_ROOT / "示例项目"
    for name in ("设计稿", "开发文档", "参考资料"):
        (tree / name).mkdir(parents=True, exist_ok=True)
    (tree / "说明.md").write_text("# 示例项目\n", encoding="utf-8")
    (tree / "开发文档" / "接口说明.md").write_text("hello", encoding="utf-8")
    assets = DEMO_ROOT / "示例素材"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "logo.png").write_text("demo", encoding="utf-8")

    folders = [
        {
            "id": "demo-project",
            "name": "示例项目",
            "path": str(tree),
            "kind": "folder",
            "category": "Development",
            "note": "演示用文件夹",
            "favorite": True,
            "createdAt": "2026-10-18T00:00:00.0000000-08:00",
        },
        {
            "id": "demo-assets",
            "name": "素材库",
            "path": str(assets),
            "kind": "folder",
            "category": "Design",
            "note": "",
            "favorite": False,
            "createdAt": "2026-10-18T00:05:00.0000000-08:00",
        },
        {
            "id": "demo-file",
            "name": "说明文档",
            "path": str(tree / "说明.md"),
            "kind": "file",
            "category": "Document",
            "note": "演示用文件",
            "favorite": False,
            "createdAt": "2026-10-18T00:10:00.0000000-08:00",
        },
    ]
    (qa_dir / "folders.json").write_text(
        json.dumps(folders, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sites = [
        {
            "id": "demo-site-1",
            "name": "示例网站",
            "url": "https://example.com/",
            "category": "工具",
            "note": "",
            "favorite": False,
            "createdAt": "2026-10-18T00:15:00.0000000-08:00",
        },
        {
            "id": "demo-site-2",
            "name": "文档中心",
            "url": "https://example.org/docs",
            "category": "Development",
            "note": "",
            "favorite": True,
            "createdAt": "2026-10-18T00:20:00.0000000-08:00",
        },
    ]
    (qa_dir / "sites.json").write_text(
        json.dumps(sites, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    settings = {
        "language": "zh",
        "globalHotkeyEnabled": True,
        "globalHotkeyId": "Ctrl + Alt + Space",
        "quickLinksHotkeyId": "Ctrl + Alt + Shift + L",
        "quickFoldersHotkeyId": "Ctrl + Alt + Shift + F",
        "launchAtStartup": False,
        "bookmarkSyncEnabled": False,
        "bookmarkCustomDir": "",
        "bookmarkDeleteMode": "ask",
        "shellContextMenuEnabled": False,
        "aiEnabled": False,
        "aiBaseUrl": "https://api.deepseek.com",
        "aiModel": "deepseek-chat",
    }
    (qa_dir / "settings.json").write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for stale in (
        "sites.json.bak",
        "folders.json.bak",
        "settings.json.bak",
        ".resourcehub-meta.json",
        ".resourcehub-ai-key",
    ):
        (qa_dir / stale).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", required=True, type=Path)
    args = parser.parse_args()
    build = args.build.resolve()
    SHOTS.mkdir(parents=True, exist_ok=True)

    kill_app()
    work = Path(tempfile.mkdtemp(prefix="rh-shots-"))
    process = None
    try:
        qa_dir = work / "app"
        shutil.copytree(build, qa_dir)
        seed(qa_dir)
        process = subprocess.Popen([str(qa_dir / "resource_hub.exe")], cwd=str(qa_dir))

        hwnd = 0
        deadline = time.time() + 30
        while time.time() < deadline:
            if process.poll() is not None:
                print("app exited during startup")
                return 1
            candidate = find_window(process.pid)
            if candidate:
                rect = window_rect(candidate)
                if rect[2] - rect[0] > 800 and rect[3] - rect[1] > 600:
                    hwnd = candidate
                    break
            time.sleep(0.2)
        if not hwnd:
            print("no main window")
            return 1
        force_foreground(hwnd)
        ready = False
        for _ in range(40):
            if list_loaded(hwnd):
                ready = True
                break
            time.sleep(0.25)
        print("  list loaded:", ready)
        move_neutral(hwnd)
        capture(hwnd, "main-window.png", crop=(0.005, 0.0, 0.982, 0.60))

        # Folder mind map panel.
        left, top, right, bottom = window_rect(hwnd)
        width, height = right - left, bottom - top
        click_at(left + width * ROW_CLICK[0], top + height * ROW_CLICK[1])
        time.sleep(1.2)
        move_neutral(hwnd)
        capture(hwnd, "folder-mindmap.png", crop=(0.535, 0.16, 0.99, 0.955))
        tap_escape()
        time.sleep(0.4)

        # Settings dialog.
        click_at(left + width * SETTINGS_GEAR[0], top + height * SETTINGS_GEAR[1])
        time.sleep(1.0)
        move_neutral(hwnd)
        capture(hwnd, "settings.png", crop=(0.286, 0.054, 0.708, 0.72))
        tap_escape()
        time.sleep(0.4)

        # Quick folders HUD (the app morphs its own window).
        key_combo(["ctrl", "alt", "shift", "f"])
        time.sleep(1.2)
        hud = find_window(process.pid)
        if hud:
            hud_rect = window_rect(hud)
            hud_w = hud_rect[2] - hud_rect[0]
            hud_h = hud_rect[3] - hud_rect[1]
            print(f"  HUD {hud_w}x{hud_h}")
            if 400 <= hud_w <= 900 and 500 <= hud_h <= 1100:
                force_foreground(hud)
                move_neutral(hud)
                capture(hud, "quick-panel.png")
                # Click the search bar so synthetic Esc reaches the HUD.
                click_at(hud_rect[0] + hud_w // 2, hud_rect[1] + 34)
                tap_escape()
        time.sleep(0.5)
        return 0
    finally:
        if process is not None and process.poll() is None:
            process.kill()
        kill_app()
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(DEMO_ROOT, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
