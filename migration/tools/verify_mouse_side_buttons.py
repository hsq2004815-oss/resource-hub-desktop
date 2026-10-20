"""Real-device check for the mouse side-button quick panels (Windows).

Starts the frozen backend against a throw-away data dir with
``mouseSideButtonsEnabled`` on and the keyboard hotkeys off, then synthesises
XBUTTON1 / XBUTTON2 with ``SendInput`` and asserts the backend emits the same
``hotkey`` events the keyboard panels use.

Usage:
    D:\\miniconda3\\python.exe migration\\tools\\verify_mouse_side_buttons.py
"""

from __future__ import annotations

import argparse
import ctypes
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKEND = (
    ROOT / "build" / "backend-exe" / "dist" / "resource_hub_backend"
    / "resource_hub_backend.exe"
)

XBUTTON1 = 0x0001
XBUTTON2 = 0x0002
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
INPUT_MOUSE = 0
CREATE_NO_WINDOW = 0x08000000

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class INPUT(ctypes.Structure):
    class _Value(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    _anonymous_ = ("value",)
    _fields_ = [("type", wintypes.DWORD), ("value", _Value)]


def send_xbutton(button: int) -> None:
    """Press and release one mouse side button."""
    for flag in (MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP):
        event = INPUT(
            type=INPUT_MOUSE,
            value=INPUT._Value(mi=MOUSEINPUT(mouseData=button, dwFlags=flag)),
        )
        if ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
            raise OSError(f"SendInput failed for {flag:#x}")


class Backend:
    def __init__(self, cmd: list[str], data_dir: Path) -> None:
        self.frames: "queue.Queue[dict]" = queue.Queue()
        self.proc = subprocess.Popen(
            [*cmd, str(data_dir)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            creationflags=CREATE_NO_WINDOW,
        )
        self._next_id = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self.frames.put(json.loads(line))
            except json.JSONDecodeError:
                print(f"  (non-JSON stdout: {line[:80]})")

    def send(self, method: str, params: dict | None = None) -> int:
        self._next_id += 1
        frame = {"id": self._next_id, "method": method, "params": params or {}}
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(frame) + "\n")
        self.proc.stdin.flush()
        return self._next_id

    def wait(self, predicate, timeout: float = 5.0, label: str = "") -> dict:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for {label or predicate}")
            try:
                frame = self.frames.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError(f"timed out waiting for {label or predicate}") from None
            if predicate(frame):
                return frame

    def close(self) -> None:
        try:
            self.send("app.shutdown")
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", type=Path, default=DEFAULT_BACKEND)
    args = parser.parse_args()
    if not args.backend.exists():
        print(f"FAIL backend not found: {args.backend}")
        return 1

    data_dir = Path(tempfile.mkdtemp(prefix="drawer_mouse_qa_"))
    (data_dir / "settings.json").write_text(
        json.dumps(
            {
                "globalHotkeyEnabled": False,
                "mouseSideButtonsEnabled": True,
                "launchAtStartup": False,
            }
        ),
        encoding="utf-8",
    )
    backend = Backend(
        [sys.executable, str(args.backend)]
        if args.backend.suffix == ".py"
        else [str(args.backend)],
        data_dir,
    )
    failures = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))

    try:
        hello_id = backend.send("app.hello")
        hello = backend.wait(lambda f: f.get("id") == hello_id, 15, "app.hello")
        check("app_hello", hello.get("result", {}).get("dataStatus") == "ok")

        start_id = backend.send("hotkey.start")
        started = backend.wait(lambda f: f.get("id") == start_id, 5, "hotkey.start")
        mouse = started.get("result", {}).get("mouseSideButtons", {})
        check("mouse_hook_registered", mouse.get("registered") is True, json.dumps(mouse))

        send_xbutton(XBUTTON1)
        event = backend.wait(
            lambda f: f.get("event") == "hotkey"
            and f.get("payload", {}).get("action") == "quickLinks",
            3,
            "quickLinks event",
        )
        check("back_button_opens_quick_links", event["payload"]["action"] == "quickLinks")

        send_xbutton(XBUTTON2)
        event = backend.wait(
            lambda f: f.get("event") == "hotkey"
            and f.get("payload", {}).get("action") == "quickFolders",
            3,
            "quickFolders event",
        )
        check("forward_button_opens_quick_folders", event["payload"]["action"] == "quickFolders")
    except Exception as exc:  # noqa: BLE001 - the run should always report
        check("unexpected_error", False, str(exc))
    finally:
        backend.close()

    print(f"{'PASS' if failures == 0 else 'FAIL'}: mouse side buttons")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
