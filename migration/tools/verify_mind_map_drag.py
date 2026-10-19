"""Phase 23 QA: the folder mind map must pan from every drag start point.

The regression this guards against: the curved-edge `CustomPaint` reported a hit
for the whole content rectangle (a `CustomPainter` without `hitTest` counts as a
hit), so every drag that started inside the map content — which is where the map
is — never reached the background pan gesture detector. Only the thin blank
margin *outside* the content rect responded, so panning felt random ("always no
reaction in the middle").

The script copies a release build to a temp folder (never touches the shipped
data), seeds one folder resource pointing at a small tree on disk, launches the
app, opens the folder mind map and drags from a control point plus three probe
points inside the map content. Each probe pans by (+60, +40) device pixels and
then back, so the rendered pixels must move and then return exactly.

Usage:
    python migration/tools/verify_mind_map_drag.py --build release\\ResourceHub-Desktop-20261018-2215
    python migration/tools/verify_mind_map_drag.py --build ... --label old --expect fail
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
from PIL import Image, ImageGrab

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESS_NAME = "resource_hub.exe"
SHOTS = REPO_ROOT / "migration" / "screenshots"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# The QA window is the fixed 1280x820 logical shell at the machine's 125% DPI,
# exactly like the other real-device scripts (fractions measured on that frame).
ROW_CLICK = (0.151, 0.234)  # first row of the resource table
FIT_BUTTON = (0.626, 0.358)  # mind map toolbar: fit view
MAP_ROI = (0.560, 0.400, 0.970, 0.930)  # map canvas inside the details panel
PROBE_DELTA = (60, 40)  # device pixels
NEUTRAL = (30, 30)  # title bar: pointer away from the Flutter content

try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4 & 0xFFFFFFFFFFFFFFFF))
except Exception:  # pragma: no cover - older Windows
    user32.SetProcessDPIAware()

user32.EnumWindows.argtypes = [
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

results: dict[str, object] = {"probes": {}, "screenshots": []}


def record(name: str, ok: bool, detail: str, **extra: object) -> None:
    results["probes"][name] = {"ok": bool(ok), "detail": detail, **extra}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def wait_until(predicate, timeout: float = 8.0, interval: float = 0.1) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def kill_app() -> None:
    subprocess.run(
        ["taskkill", "/IM", PROCESS_NAME, "/F"],
        capture_output=True,
        text=True,
        errors="ignore",
    )
    wait_until(lambda: not _pids(), timeout=6.0)


def _pids() -> list[int]:
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {PROCESS_NAME}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    ).stdout
    pids: list[int] = []
    for line in out.splitlines():
        parts = [part.strip('"') for part in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == PROCESS_NAME.lower():
            try:
                pids.append(int(parts[1]))
            except ValueError:
                continue
    return pids


def find_window(pid: int) -> int:
    """Largest visible, titled top-level window of the process (the main one)."""
    candidates: list[tuple[int, int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid:
            left, top, right, bottom = window_rect(hwnd)
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            candidates.append(((right - left) * (bottom - top), hwnd, buffer.value))
        return True

    user32.EnumWindows(callback, 0)
    candidates.sort(reverse=True)
    if not candidates:
        return 0
    return candidates[0][1]


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def force_foreground(hwnd: int) -> None:
    """Keep the QA window topmost so captures are not occluded by other apps."""
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    topmost = wintypes.HWND(-1)
    flags = 0x0002 | 0x0001  # NOMOVE | NOSIZE
    user32.SetWindowPos(hwnd, topmost, 0, 0, 0, 0, flags)
    user32.SetForegroundWindow(hwnd)
    if user32.GetForegroundWindow() != hwnd:
        foreground = user32.GetForegroundWindow()
        foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        this_thread = kernel32.GetCurrentThreadId()
        if foreground_thread and foreground_thread != this_thread:
            user32.AttachThreadInput(this_thread, foreground_thread, True)
            try:
                user32.SetForegroundWindow(hwnd)
            finally:
                user32.AttachThreadInput(this_thread, foreground_thread, False)
    time.sleep(0.3)


def move_to(x: float, y: float) -> None:
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)


def click_at(x: float, y: float) -> None:
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.45)


def drag(start: tuple[float, float], delta: tuple[int, int], steps: int = 8) -> None:
    x, y = int(start[0]), int(start[1])
    user32.SetCursorPos(x, y)
    time.sleep(0.10)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.06)
    for index in range(1, steps + 1):
        user32.SetCursorPos(
            x + delta[0] * index // steps,
            y + delta[1] * index // steps,
        )
        time.sleep(0.014)
    time.sleep(0.10)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.40)


def capture(hwnd: int) -> Image.Image:
    left, top, right, bottom = window_rect(hwnd)
    return ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)


def roi_box(width: int, height: int) -> tuple[int, int, int, int]:
    return (
        int(width * MAP_ROI[0]),
        int(height * MAP_ROI[1]),
        int(width * MAP_ROI[2]),
        int(height * MAP_ROI[3]),
    )


def crop_roi(image: Image.Image) -> Image.Image:
    return image.crop(roi_box(image.width, image.height)).convert("RGB")


def changed_ratio(before: Image.Image, after: Image.Image, threshold: int = 10) -> float:
    a = np.asarray(before, dtype=np.int16)
    b = np.asarray(after, dtype=np.int16)
    if a.shape != b.shape:
        return 1.0
    return float((np.abs(a - b).max(axis=2) > threshold).mean())


def text_bbox(roi: Image.Image) -> tuple[int, int, int, int] | None:
    """Bounding box of the dark node text inside the map ROI."""
    gray = np.asarray(roi.convert("L"))
    ys, xs = np.where(gray < 150)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def dark_columns(roi: Image.Image, top: int, bottom: int, left: int, right: int):
    """Merged x ranges that contain node text inside the given bbox."""
    gray = np.asarray(roi.convert("L"))[top : bottom + 1, left : right + 1]
    columns = (gray < 150).any(axis=0)
    ranges: list[list[int]] = []
    start: int | None = None
    for index, present in enumerate(columns):
        if present and start is None:
            start = index
        elif not present and start is not None:
            ranges.append([start, index - 1])
            start = None
    if start is not None:
        ranges.append([start, len(columns) - 1])
    merged: list[list[int]] = []
    for span in ranges:
        if merged and span[0] - merged[-1][1] <= 10:
            merged[-1][1] = span[1]
        else:
            merged.append(span)
    return [[left + a, left + b] for a, b in merged]


def seed_data(qa_dir: Path) -> None:
    tree = qa_dir / "qa-tree"
    for name in ("alpha", "beta", "gamma"):
        (tree / name).mkdir(parents=True, exist_ok=True)
    (tree / "readme.txt").write_text("phase 23 qa", encoding="utf-8")
    folders = [
        {
            "id": "qa-mind-map",
            "name": "QA 地图",
            "path": str(tree),
            "kind": "folder",
            "category": "System",
            "note": "",
            "favorite": True,
            "createdAt": "2026-10-18T00:00:00.0000000-08:00",
        }
    ]
    (qa_dir / "folders.json").write_text(
        json.dumps(folders, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    settings = {
        "language": "zh",
        "globalHotkeyEnabled": False,
        "globalHotkeyId": "Ctrl + Alt + Space",
        "quickLinksHotkeyId": "Ctrl + Shift + G",
        "quickFoldersHotkeyId": "Ctrl + Shift + V",
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
    for stale in ("sites.json", "sites.json.bak", "folders.json.bak", "settings.json.bak"):
        (qa_dir / stale).unlink(missing_ok=True)
    meta = qa_dir / ".resourcehub-meta.json"
    meta.unlink(missing_ok=True)
    (qa_dir / ".resourcehub-ai-key").unlink(missing_ok=True)


def prepare(build: Path, work: Path) -> Path:
    qa_dir = work / "app"
    shutil.copytree(build, qa_dir)
    seed_data(qa_dir)
    return qa_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--label", default="new")
    parser.add_argument("--expect", choices=("pass", "fail"), default="pass")
    args = parser.parse_args()
    build = args.build.resolve()

    print(f"QA build: {build}")
    kill_app()
    work = Path(tempfile.mkdtemp(prefix="rh-mindmap-qa-"))
    process = None
    try:
        qa_dir = prepare(build, work)
        exe = qa_dir / "resource_hub.exe"
        process = subprocess.Popen([str(exe)], cwd=str(qa_dir))

        hwnd = 0
        deadline = time.time() + 30.0
        while time.time() < deadline:
            if process.poll() is not None:
                print("  app exited before showing a window")
                return 1
            candidate = find_window(process.pid)
            if candidate:
                candidate_rect = window_rect(candidate)
                candidate_width = candidate_rect[2] - candidate_rect[0]
                candidate_height = candidate_rect[3] - candidate_rect[1]
                if candidate_width > 800 and candidate_height > 600:
                    hwnd = candidate
                    break
            time.sleep(0.2)
        if not hwnd:
            print("  no window: app did not start")
            return 1
        force_foreground(hwnd)
        left, top, right, bottom = window_rect(hwnd)
        width, height = right - left, bottom - top
        print(f"  window {width}x{height} at ({left},{top})")
        record("window_present", width > 800 and height > 600, f"{width}x{height}")

        # Open the first resource's details panel -> folder mind map. The first
        # click can land while the backend is still connecting, so retry until
        # the map actually renders.
        hwnd_ready = False
        bbox = None
        for _attempt in range(8):
            click_at(left + width * ROW_CLICK[0], top + height * ROW_CLICK[1])
            time.sleep(1.0)
            move_to(left + NEUTRAL[0], top + NEUTRAL[1])
            time.sleep(0.5)
            image = capture(hwnd)
            roi = crop_roi(image)
            bbox = text_bbox(roi)
            if bbox is not None:
                hwnd_ready = True
                break
            time.sleep(1.0)
        image.save(SHOTS / f"phase23-{args.label}-after-click.png")
        if not hwnd_ready or bbox is None:
            record("mind_map_opened", False, "no node text in the map region")
            return 1
        print(f"  node text bbox in ROI: {bbox}")
        record("mind_map_opened", True, f"node text bbox {bbox}")

        roi_w = roi.width
        roi_h = roi.height
        bbox_left, bbox_top, _, bbox_bottom = bbox
        tree_center_y = (bbox_top + bbox_bottom) // 2

        probes: dict[str, tuple[float, float]] = {}
        # Control: blank canvas left of the content (worked before the fix too).
        probes["control"] = (left + width * MAP_ROI[0] + 14, top + height * MAP_ROI[1] + roi_h * 0.5)
        # Margin above the topmost node text: still inside the content rect.
        margin_y = bbox_top - 20
        if margin_y > 12:
            probes["margin_above"] = (left + width * MAP_ROI[0] + bbox_left + 6, top + height * MAP_ROI[1] + margin_y)
        # Root node card (left column, vertically centred on the tree).
        probes["root_card"] = (left + width * MAP_ROI[0] + bbox_left - 4, top + height * MAP_ROI[1] + tree_center_y)
        # Blank gap between the root card and the children column.
        columns = dark_columns(roi, bbox_top, bbox_bottom, bbox_left, bbox[2])
        print(f"  dark columns: {columns}")
        if len(columns) >= 2:
            gap_x = (columns[0][1] + columns[-1][0]) // 2
            probes["column_gap"] = (left + width * MAP_ROI[0] + gap_x, top + height * MAP_ROI[1] + tree_center_y)
        else:
            record("column_gap", False, "could not locate the two node columns")
        record("probes_ready", len(probes) >= 3, f"probes={sorted(probes)}")

        fit_x = left + width * FIT_BUTTON[0]
        fit_y = top + height * FIT_BUTTON[1]
        regression_probes: list[str] = []
        for name, point in probes.items():
            click_at(fit_x, fit_y)
            move_to(left + NEUTRAL[0], top + NEUTRAL[1])
            time.sleep(0.45)
            before = crop_roi(capture(hwnd))
            drag(point, PROBE_DELTA)
            move_to(left + NEUTRAL[0], top + NEUTRAL[1])
            time.sleep(0.45)
            after = crop_roi(capture(hwnd))
            drag((point[0] + PROBE_DELTA[0], point[1] + PROBE_DELTA[1]), (-PROBE_DELTA[0], -PROBE_DELTA[1]))
            move_to(left + NEUTRAL[0], top + NEUTRAL[1])
            time.sleep(0.45)
            restored = crop_roi(capture(hwnd))
            moved = changed_ratio(before, after)
            returned = changed_ratio(before, restored)
            ok = moved > 0.01 and returned < 0.004
            record(
                f"drag_{name}",
                ok,
                f"start=({int(point[0]-left)},{int(point[1]-top)}) moved={moved:.3f} restored={returned:.3f}",
                moved=round(moved, 4),
                returned=round(returned, 4),
            )
            if name != "control":
                regression_probes.append(f"drag_{name}")
            if name == "margin_above" or (name == "control"):
                suffix = f"{args.label}-{name}"
                image_before = Image.fromarray(np.asarray(before))
                image_after = Image.fromarray(np.asarray(after))
                before_path = SHOTS / f"phase23-drag-{suffix}-before.png"
                after_path = SHOTS / f"phase23-drag-{suffix}-after.png"
                image_before.save(before_path)
                image_after.save(after_path)
                results["screenshots"] += [str(before_path), str(after_path)]
                print(f"  screenshot -> {before_path.name}, {after_path.name}")

        control_probe = results["probes"].get("drag_control", {})
        control_ok = bool(control_probe.get("ok"))
        control_panned = float(control_probe.get("moved", 0.0)) > 0.01
        regression_failed = [
            name for name in regression_probes if not results["probes"][name]["ok"]
        ]
        if args.expect == "pass":
            overall = control_ok and len(regression_failed) == 0
        else:
            # Old build: the control drag still pans, while at least two drags
            # that start inside the map content must do nothing.
            overall = control_panned and len(regression_failed) >= 2
        results["control_panned"] = control_panned
        results["expect"] = args.expect
        results["overall_ok"] = overall
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if overall else 1
    finally:
        if process is not None and process.poll() is None:
            process.kill()
        kill_app()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
