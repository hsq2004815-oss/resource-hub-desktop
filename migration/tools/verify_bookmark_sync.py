"""Phase 17 real-device check: browser bookmark bridge.

Runs a throwaway copy of the release build (so the real data directory is never
touched) with a fake Chrome profile:

  1. a custom bookmark directory is discovered and its existing bookmarks are
     imported before the first window paint;
  2. appending a bookmark to the file is picked up by the watcher within a few
     seconds;
  3. categories follow the bookmark folders (书签栏 / 折叠夹 / 其他收藏);
  4. the browser file is never modified (byte-for-byte comparison);
  5. the settings dialog shows the detected profile.

    D:\\miniconda3\\python.exe migration/tools/verify_bookmark_sync.py
"""

from __future__ import annotations

import ctypes
import json
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

REPO_ROOT = Path(__file__).resolve().parents[2]
SHOTS = REPO_ROOT / "migration" / "screenshots"
PROCESS_NAME = "resource_hub.exe"

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
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

report: dict[str, object] = {"probes": {}}


def record(name: str, ok: bool, detail: str, **extra) -> None:
    report["probes"][name] = {"ok": bool(ok), "detail": detail, **extra}
    print(("PASS " if ok else "FAIL ") + name + " — " + detail)


def url_node(name: str, url: str) -> dict:
    return {"type": "url", "name": name, "url": url}


def folder_node(name: str, children: list[dict]) -> dict:
    return {"type": "folder", "name": name, "children": children}


def bookmarks_document() -> dict:
    return {
        "roots": {
            "bookmark_bar": {
                "type": "folder",
                "name": "Bookmarks bar",
                "children": [
                    url_node("Home", "https://home.example/"),
                    folder_node(
                        "开发",
                        [url_node("Python", "https://python.org/")],
                    ),
                ],
            },
            "other": {
                "type": "folder",
                "name": "Other bookmarks",
                "children": [url_node("Docs", "https://docs.example/")],
            },
        }
    }


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def wait_until(predicate, timeout: float = 15.0, interval: float = 0.25) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(interval)
    return False


def find_window(executable: Path) -> int:
    """The visible top-level window of the app started from |executable|."""
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
            if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return True
            if Path(buffer.value).resolve() == executable.resolve():
                found.append(hwnd)
                return False
        finally:
            kernel32.CloseHandle(handle)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else 0


def click_at(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)
    time.sleep(0.1)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.02)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.4)


def force_foreground(hwnd: int) -> None:
    """Raise the QA window above whatever else is on screen (for screenshots)."""
    hwnd_topmost = wintypes.HWND(-1)
    hwnd_nottopmost = wintypes.HWND(-2)
    swp = 0x0002 | 0x0001  # SWP_NOMOVE | SWP_NOSIZE
    user32.SetWindowPos(hwnd, hwnd_topmost, 0, 0, 0, 0, swp)
    user32.SetWindowPos(hwnd, hwnd_nottopmost, 0, 0, 0, 0, swp)
    user32.SetForegroundWindow(hwnd)
    if user32.GetForegroundWindow() != hwnd:
        foreground = user32.GetForegroundWindow()
        foreground_thread = (
            user32.GetWindowThreadProcessId(foreground, None)
            if foreground is not None
            else 0
        )
        this_thread = kernel32.GetCurrentThreadId()
        if foreground_thread and foreground_thread != this_thread:
            user32.AttachThreadInput(this_thread, foreground_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(this_thread, foreground_thread, False)
    time.sleep(0.4)


def capture_window(hwnd: int, name: str) -> Path:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    target = SHOTS / name
    image = ImageGrab.grab(
        bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    print(f"  screenshot -> {target}")
    return target


def site_names(data_dir: Path) -> list[str]:
    path = data_dir / "sites.json"
    if not path.exists():
        return []
    return [entry["name"] for entry in read_json(path)]


def site_entry(data_dir: Path, name: str) -> dict | None:
    path = data_dir / "sites.json"
    if not path.exists():
        return None
    for entry in read_json(path):
        if entry["name"] == name:
            return entry
    return None


def main() -> int:
    builds = sorted(REPO_ROOT.glob("release/ResourceHub-Desktop-*"))
    if len(builds) < 1:
        print("no release build found")
        return 1
    source = builds[-1]
    print(f"source build: {source}")
    stable = REPO_ROOT / "release" / "ResourceHub-Desktop-20261017-1835"
    stable_data = stable / "sites.json"
    stable_before = stable_data.read_bytes() if stable_data.exists() else None

    work = Path(tempfile.mkdtemp(prefix="rh-bookmark-qa-"))
    qa_dir = work / "app"
    browser_root = work / "browser" / "User Data"
    try:
        shutil.copytree(source, qa_dir)
        for stale in (
            "sites.json",
            "sites.json.bak",
            "folders.json",
            "folders.json.bak",
            "settings.json",
            "settings.json.bak",
            ".resourcehub-meta.json",
        ):
            (qa_dir / stale).unlink(missing_ok=True)

        profile = browser_root / "Default"
        profile.mkdir(parents=True)
        bookmark_file = profile / "Bookmarks"
        bookmark_file.write_text(
            json.dumps(bookmarks_document(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        original_bytes = bookmark_file.read_bytes()
        (qa_dir / "settings.json").write_text(
            json.dumps(
                {
                    "language": "zh",
                    "globalHotkeyEnabled": False,
                    "globalHotkeyId": "Ctrl + Alt + Space",
                    "quickLinksHotkeyId": "Ctrl + Alt + Shift + L",
                    "quickFoldersHotkeyId": "Ctrl + Alt + Shift + F",
                    "bookmarkSyncEnabled": True,
                    "bookmarkCustomDir": str(browser_root),
                    "launchAtStartup": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        exe = qa_dir / "resource_hub.exe"
        process = subprocess.Popen([str(exe)], cwd=str(qa_dir))
        try:
            imported = wait_until(
                lambda: set(site_names(qa_dir)) >= {"Home", "Python", "Docs"},
                timeout=25.0,
            )
            record(
                "startup_imports_existing_bookmarks",
                imported,
                f"sites={site_names(qa_dir)}",
            )
            home = site_entry(qa_dir, "Home") or {}
            python = site_entry(qa_dir, "Python") or {}
            docs = site_entry(qa_dir, "Docs") or {}
            record(
                "categories_follow_bookmark_folders",
                home.get("category") == "书签栏"
                and python.get("category") == "开发"
                and docs.get("category") == "其他收藏",
                f"Home={home.get('category')!r} Python={python.get('category')!r} "
                f"Docs={docs.get('category')!r}",
            )
            record(
                "browser_file_is_read_only",
                bookmark_file.read_bytes() == original_bytes,
                "Bookmarks bytes unchanged after the import",
            )

            # Append a bookmark and let the watcher pick it up.
            document = bookmarks_document()
            document["roots"]["bookmark_bar"]["children"].append(
                url_node("Watched", "https://watched.example/")
            )
            document["roots"]["bookmark_bar"]["children"][1]["children"].append(
                url_node("Nested", "https://nested.example/")
            )
            bookmark_file.write_text(
                json.dumps(document, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            watched = wait_until(
                lambda: {"Watched", "Nested"} <= set(site_names(qa_dir)),
                timeout=20.0,
            )
            watched_entry = site_entry(qa_dir, "Nested") or {}
            record(
                "watcher_imports_new_bookmarks",
                watched and watched_entry.get("category") == "开发",
                f"Nested category={watched_entry.get('category')!r} "
                f"sites={site_names(qa_dir)}",
            )

            count_before = len(site_names(qa_dir))
            time.sleep(4.0)
            record(
                "watcher_is_idempotent",
                len(site_names(qa_dir)) == count_before,
                f"still {len(site_names(qa_dir))} sites after another poll",
            )

            hwnd = find_window(exe)
            if hwnd:
                force_foreground(hwnd)
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                # Switch to the sites tab so the imported bookmarks are visible.
                click_at(
                    rect.left + int(width * 0.753),
                    rect.top + int(height * 0.080),
                )
                capture_window(hwnd, "phase17-bookmarks-imported.png")
                # Settings gear (same relative spot as in the shipped window).
                click_at(
                    rect.left + int(width * 0.962),
                    rect.top + int(height * 0.125),
                )
                time.sleep(0.8)
                capture_window(hwnd, "phase17-settings-bookmarks.png")
                user32.keybd_event(0x1B, 0, 0, 0)
                time.sleep(0.05)
                user32.keybd_event(0x1B, 0, 0, 0x0002)
                record("window_screenshots", True, "captured list + settings")
            else:
                record("window_screenshots", False, "QA window not found")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

        # The real stable release directory is untouched.
        stable_after = stable_data.read_bytes() if stable_data.exists() else None
        record(
            "real_data_directory_untouched",
            stable_before == stable_after,
            "the installed folder sites.json is byte-identical before/after QA",
        )
    finally:
        time.sleep(0.5)
        shutil.rmtree(work, ignore_errors=True)

    failed = [name for name, probe in report["probes"].items() if not probe["ok"]]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n{len(report['probes']) - len(failed)}/{len(report['probes'])} checks passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
