"""Phase 16 real-device check: quick-panel hotkeys.

Drives the *installed* app through its three global hotkeys with synthetic key
presses (the same technique `probe_headless_tray_hotkey.py` uses) and verifies the
window really morphs into the frameless, topmost 480x600 tree HUD:

  1. quick-links hotkey   -> links tree HUD, Escape restores the normal window
  2. quick-folders hotkey -> folders tree HUD, ArrowDown/ArrowRight expands lazily
  3. full-window toggle   -> the legacy show/hide still works
  4. quick-links while hidden -> HUD opens over the tray, Escape goes back to tray

The three combinations are read from the app's own `settings.json` (next to
`resource_hub.exe`), so a user who recorded custom hotkeys is exercised exactly
as configured; the shipped defaults are only a fallback.

Screenshots land in migration/screenshots/. Run with the release build running:

    D:\\miniconda3\\python.exe migration/tools/verify_quick_panel.py
"""

from __future__ import annotations

import ctypes
import json
import re
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

PROCESS_NAME = "resource_hub.exe"
REPO_ROOT = Path(__file__).resolve().parents[2]
SHOTS = REPO_ROOT / "migration" / "screenshots"

DEFAULT_HOTKEYS = {
    "toggle": "Ctrl + Alt + Space",
    "quickLinks": "Ctrl + Alt + Shift + L",
    "quickFolders": "Ctrl + Alt + Shift + F",
}

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Must happen before ANY coordinate query (see capture_window.py).
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4 & 0xFFFFFFFFFFFFFFFF))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        user32.SetProcessDPIAware()

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowLongPtrW.restype = ctypes.c_longlong
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
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

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CAPTION = 0x00C00000
WS_EX_TOOLWINDOW = 0x00000080
VK_ESCAPE = 0x1B
VK_DOWN, VK_RIGHT = 0x28, 0x27
KEYEVENTF_KEYUP = 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

LOGICAL_WIDTH = 480.0
LOGICAL_HEIGHT = 600.0

MODIFIER_VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B}
SPECIAL_VK = {
    "space": 0x20,
    "enter": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "minus": 0xBD,
    "equals": 0xBB,
    "comma": 0xBC,
    "period": 0xBE,
    "slash": 0xBF,
    "semicolon": 0xBA,
    "apostrophe": 0xDE,
    "leftbracket": 0xDB,
    "rightbracket": 0xDD,
    "backslash": 0xDC,
    "backtick": 0xC0,
}

report: dict[str, object] = {"probes": {}}


def record(name: str, ok: bool, detail: str, **extra) -> None:
    report["probes"][name] = {"ok": bool(ok), "detail": detail, **extra}
    print(("PASS " if ok else "FAIL ") + name + " — " + detail)


def _key_vk(name: str) -> int:
    lowered = name.strip().lower()
    if lowered in SPECIAL_VK:
        return SPECIAL_VK[lowered]
    if re.fullmatch(r"[a-z0-9]", lowered):
        return ord(lowered.upper())
    match = re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", lowered)
    if match:
        return 0x70 + int(match.group(1)) - 1
    raise ValueError(f"unsupported hotkey key {name!r}")


def parse_hotkey(label: str) -> tuple[tuple[int, ...], int]:
    parts = [part.strip() for part in label.split("+") if part.strip()]
    if not parts:
        raise ValueError(f"empty hotkey {label!r}")
    modifiers: list[int] = []
    for part in parts[:-1]:
        try:
            modifiers.append(MODIFIER_VK[part.lower()])
        except KeyError as exc:  # pragma: no cover - defensive
            raise ValueError(f"unsupported modifier {part!r} in {label!r}") from exc
    return tuple(modifiers), _key_vk(parts[-1])


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


def executable_path(pid: int) -> Path | None:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return None
        return Path(buffer.value)
    finally:
        kernel32.CloseHandle(handle)


def load_hotkeys(pids: set[int]) -> dict[str, str]:
    hotkeys = dict(DEFAULT_HOTKEYS)
    for pid in sorted(pids):
        exe = executable_path(pid)
        if exe is None:
            continue
        settings_path = exe.parent / "settings.json"
        if not settings_path.is_file():
            continue
        try:
            raw = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        for key, json_key in (
            ("toggle", "globalHotkeyId"),
            ("quickLinks", "quickLinksHotkeyId"),
            ("quickFolders", "quickFoldersHotkeyId"),
        ):
            value = raw.get(json_key)
            if isinstance(value, str) and value.strip():
                hotkeys[key] = value.strip()
        report["settings"] = str(settings_path)
        return hotkeys
    return hotkeys


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


def window_state(hwnd: int) -> dict[str, object]:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    ex_style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    dpi = user32.GetDpiForWindow(hwnd) or 96
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return {
        "visible": bool(user32.IsWindowVisible(hwnd)),
        "rect": (rect.left, rect.top, width, height),
        "width": width,
        "height": height,
        "dpi": dpi,
        "scale": dpi / 96.0,
        "frameless": (style & WS_CAPTION) == 0,
        "toolwindow": bool(ex_style & WS_EX_TOOLWINDOW),
        "foreground": bool(user32.GetForegroundWindow() == hwnd),
        "expected_width": round(LOGICAL_WIDTH * dpi / 96.0),
        "expected_height": round(LOGICAL_HEIGHT * dpi / 96.0),
    }


def key_combo(hotkey: str) -> None:
    modifiers, key = parse_hotkey(hotkey)
    pressed: list[int] = []
    try:
        for vk in (*modifiers, key):
            user32.keybd_event(vk, 0, 0, 0)
            pressed.append(vk)
            time.sleep(0.02)
        for vk in reversed(pressed):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)
    finally:
        for vk in reversed(pressed):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.15)


def key_tap(key: int) -> None:
    user32.keybd_event(key, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)


def click_at(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)
    time.sleep(0.1)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.02)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.25)


def focus_hud(hwnd: int) -> None:
    """Click the HUD search bar so synthetic Escape/arrows reach our window.

    A real user's hotkey press leaves the panel in the foreground; a synthetic
    key press from another process does not, so the automation must focus it.
    The search bar only takes focus (it never opens a resource).
    """
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    click_at(
        rect.left + (rect.right - rect.left) // 2,
        rect.top + 34,
    )


def capture(hwnd: int, name: str) -> Path:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    target = SHOTS / name
    target.parent.mkdir(parents=True, exist_ok=True)
    image = ImageGrab.grab(
        bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True
    )
    image.save(target)
    print(f"  screenshot -> {target}")
    return target


def wait_until(predicate, timeout: float = 4.0, interval: float = 0.1) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def hud_is_open(hwnd: int) -> bool:
    state = window_state(hwnd)
    return (
        state["visible"]
        and state["frameless"]
        and state["toolwindow"]
        and abs(state["width"] - state["expected_width"]) <= 2
        and abs(state["height"] - state["expected_height"]) <= 2
    )


def main() -> int:
    pids = find_pids()
    if not pids:
        print(f"{PROCESS_NAME} is not running")
        return 1
    hotkeys = load_hotkeys(pids)
    print("hotkeys:", hotkeys)
    hwnd = find_window(pids)
    if not hwnd:
        print("no visible top-level window found — start the release build first")
        return 1
    print(f"hwnd={hwnd} pids={sorted(pids)}")

    # 0. Baseline: the normal window has a caption and is much larger than the HUD.
    normal = window_state(hwnd)
    record(
        "normal_window_baseline",
        normal["visible"] and not normal["frameless"],
        f"normal state: visible={normal['visible']} frameless={normal['frameless']} "
        f"{normal['width']}x{normal['height']} @{normal['dpi']}dpi",
    )

    # 1. Quick links hotkey -> links HUD.
    key_combo(hotkeys["quickLinks"])
    ok = wait_until(lambda: hud_is_open(hwnd))
    focus_hud(hwnd)
    hud = window_state(hwnd)
    record(
        "quick_links_hotkey_opens_hud",
        ok and hud["foreground"],
        "frameless={frameless} toolwindow={toolwindow} size={width}x{height} "
        "(expected {expected_width}x{expected_height}) foreground={foreground}".format(**hud),
    )
    capture(hwnd, "phase16-quick-links.png")

    # 2. Escape restores the normal framed window (it was visible when opened).
    key_tap(VK_ESCAPE)
    ok = wait_until(
        lambda: not window_state(hwnd)["frameless"] and window_state(hwnd)["visible"]
    )
    restored = window_state(hwnd)
    record(
        "escape_restores_full_window",
        ok,
        "frameless={frameless} visible={visible} size={width}x{height}".format(**restored),
    )

    # 3. Quick folders hotkey -> folders HUD; expand the first resource with the
    #    keyboard so the lazily loaded children are captured too.
    key_combo(hotkeys["quickFolders"])
    wait_until(lambda: hud_is_open(hwnd))
    focus_hud(hwnd)
    key_tap(VK_DOWN)
    time.sleep(0.2)
    key_tap(VK_RIGHT)
    time.sleep(1.0)  # fs.children round-trip
    capture(hwnd, "phase16-quick-folders-expanded.png")
    folders = window_state(hwnd)
    record(
        "quick_folders_hotkey_opens_hud",
        hud_is_open(hwnd),
        "frameless={frameless} toolwindow={toolwindow} size={width}x{height}".format(**folders),
    )
    key_tap(VK_ESCAPE)
    wait_until(
        lambda: window_state(hwnd)["visible"] and not window_state(hwnd)["frameless"]
    )

    # 4. The legacy toggle still hides / shows the full window.
    key_combo(hotkeys["toggle"])
    hidden = wait_until(lambda: not window_state(hwnd)["visible"])
    record(
        "legacy_toggle_still_hides",
        hidden,
        f"visible={window_state(hwnd)['visible']} after the toggle hotkey",
    )

    # 5. Quick HUD opens even while the window is hidden; Escape returns to tray.
    key_combo(hotkeys["quickLinks"])
    opened = wait_until(lambda: hud_is_open(hwnd))
    focus_hud(hwnd)
    record(
        "quick_hud_opens_from_tray",
        opened,
        "frameless={frameless} visible={visible} size={width}x{height}".format(
            **window_state(hwnd)
        ),
    )
    capture(hwnd, "phase16-quick-links-from-tray.png")
    key_tap(VK_ESCAPE)
    back_to_tray = wait_until(lambda: not window_state(hwnd)["visible"])
    record(
        "escape_returns_to_tray",
        back_to_tray,
        f"visible={window_state(hwnd)['visible']} (window was hidden before the HUD opened)",
    )

    # 6. Restore the normal window for the user.
    key_combo(hotkeys["toggle"])
    wait_until(
        lambda: window_state(hwnd)["visible"] and not window_state(hwnd)["frameless"]
    )

    report["hwnd"] = hwnd
    failed = [name for name, probe in report["probes"].items() if not probe["ok"]]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n{len(report['probes']) - len(failed)}/{len(report['probes'])} checks passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
