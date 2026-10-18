"""Phase 2 probe: can the tray icon and the global hotkey survive WITHOUT a Tk message loop?

Loads the real `resource_hub.pyw` as a module (no Tk root is ever created),
then exercises `GlobalHotkeyListener` and `pystray.Icon.run_detached()`.

Run with the interpreter that has tkinterdnd2/pystray installed:
    D:\\miniconda3\\python.exe migration/probes/probe_headless_tray_hotkey.py

Exit code 0 = all probes passed. Prints a JSON report to stdout.
"""

from __future__ import annotations

import ctypes
import importlib.util
import json
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "resource_hub.pyw"

# A combination that is very unlikely to be taken by anything else on this machine.
PROBE_HOTKEY = "Ctrl + Alt + Shift + F12"

report: dict[str, object] = {"module": str(MODULE_PATH), "probes": {}}


def record(name: str, ok: bool, detail: str, **extra) -> None:
    report["probes"][name] = {"ok": ok, "detail": detail, **extra}


def load_module():
    spec = importlib.util.spec_from_loader(
        "resource_hub_probe", importlib.machinery.SourceFileLoader("resource_hub_probe", str(MODULE_PATH))
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["resource_hub_probe"] = module
    spec.loader.exec_module(module)
    return module


def probe_no_tk_root(mod) -> None:
    """Confirm nothing created a Tk root as a side effect of importing."""
    try:
        import tkinter as tk

        roots = getattr(tk, "_default_root", None)
        ok = roots is None
        record("import_without_tk_root", ok, f"tk._default_root={roots!r}")
    except Exception as exc:  # pragma: no cover
        record("import_without_tk_root", False, f"{type(exc).__name__}: {exc}")


def probe_hotkey(mod) -> None:
    q: queue.SimpleQueue[str] = queue.SimpleQueue()
    listener = mod.GlobalHotkeyListener(q, PROBE_HOTKEY)

    started = listener.start()
    record(
        "hotkey_register_without_tk",
        bool(started),
        f"GlobalHotkeyListener.start() -> {started} for {PROBE_HOTKEY!r}",
        thread_name=listener.thread.name if listener.thread else None,
    )
    if not started:
        return

    # Simulate a real key press so we exercise WM_HOTKEY delivery, not just registration.
    user32 = ctypes.windll.user32
    VK_CONTROL, VK_MENU, VK_SHIFT, VK_F12 = 0x11, 0x12, 0x10, 0x7B
    KEYEVENTF_KEYUP = 0x0002
    pressed = []
    try:
        for vk in (VK_CONTROL, VK_MENU, VK_SHIFT, VK_F12):
            user32.keybd_event(vk, 0, 0, 0)
            pressed.append(vk)
            time.sleep(0.02)
        for vk in reversed(pressed):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)
    finally:
        for vk in reversed(pressed):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

    got = None
    deadline = time.time() + 3.0
    while time.time() < deadline:
        try:
            got = q.get(timeout=0.1)
            break
        except queue.Empty:
            continue
    record(
        "hotkey_delivers_wm_hotkey",
        got == "toggle",
        f"queue received {got!r} after simulated Ctrl+Alt+Shift+F12",
    )

    listener.stop()
    time.sleep(0.3)
    record(
        "hotkey_unregister_on_stop",
        not listener.registered,
        f"listener.registered={listener.registered} after stop(); thread alive="
        f"{listener.thread.is_alive() if listener.thread else None}",
    )

    # Re-register the same combo immediately: proves the previous registration was released.
    q2: queue.SimpleQueue[str] = queue.SimpleQueue()
    again = mod.GlobalHotkeyListener(q2, PROBE_HOTKEY)
    ok_again = again.start()
    record(
        "hotkey_reacquire_after_release",
        bool(ok_again),
        f"second GlobalHotkeyListener.start() -> {ok_again} (same combo, no manual cleanup)",
    )
    again.stop()


def probe_single_instance_guard(mod) -> None:
    """The mutex guard has no Tk dependency either; verify it acquires headlessly."""
    guard = mod.SingleInstanceGuard(mod.APP_MUTEX_NAME + ".Probe")
    first = guard.acquire()
    second_guard = mod.SingleInstanceGuard(mod.APP_MUTEX_NAME + ".Probe")
    second = second_guard.acquire()
    record(
        "single_instance_mutex_headless",
        bool(first) and not bool(second),
        f"first acquire={first}, second concurrent acquire={second} (expected True/False)",
    )
    second_guard.release()
    guard.release()


def probe_tray(mod) -> None:
    try:
        from PIL import Image
        import pystray
    except Exception as exc:
        record("tray_run_detached_without_tk", False, f"import failed: {type(exc).__name__}: {exc}")
        return

    image = Image.new("RGBA", (64, 64), (47, 111, 237, 255))
    clicked = threading.Event()

    icon = pystray.Icon(
        "resource_hub_probe",
        image,
        "Resource Hub Probe",
        menu=pystray.Menu(pystray.MenuItem("probe", lambda *_: clicked.set())),
    )
    try:
        icon.run_detached()
        deadline = time.time() + 5.0
        while time.time() < deadline and not icon.visible:
            time.sleep(0.05)
        record(
            "tray_run_detached_without_tk",
            bool(icon.visible),
            f"pystray.Icon.run_detached() visible={icon.visible} with no Tk root present",
        )
    except Exception as exc:
        record("tray_run_detached_without_tk", False, f"{type(exc).__name__}: {exc}")
    finally:
        try:
            icon.stop()
        except Exception:
            pass


def main() -> int:
    if os.name != "nt":
        print(json.dumps({"error": "windows-only probe"}, indent=2))
        return 2

    try:
        mod = load_module()
    except BaseException as exc:
        print(
            json.dumps(
                {
                    "fatal": f"could not load resource_hub.pyw: {type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1

    for fn in (probe_no_tk_root, probe_single_instance_guard, probe_hotkey, probe_tray):
        try:
            fn(mod)
        except BaseException as exc:
            record(fn.__name__, False, f"probe crashed: {type(exc).__name__}: {exc}")

    failed = [k for k, v in report["probes"].items() if not v["ok"]]
    report["passed"] = not failed
    report["failed_probes"] = failed
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
