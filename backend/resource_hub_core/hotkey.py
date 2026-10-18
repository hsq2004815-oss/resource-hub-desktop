"""Global hotkey listener — Tk-free.

Ported from ``GlobalHotkeyListener`` (``resource_hub.pyw:657-708``). That class
was already correct for a headless backend: it runs its own thread, forces a
thread message queue with ``PeekMessageW``, registers on that thread, and pumps
``GetMessageW`` itself. Nothing here depends on Tk.

The only change is the delivery mechanism: instead of pushing onto a queue that
a Tk ``after()`` loop drains, the caller supplies ``on_press``. Phase 4 turns
that into a JSON-Lines event.
"""

from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes
from typing import Callable

from .normalize import parse_hotkey_id

APP_HOTKEY_ID = 0xB123
APP_HOTKEY_PROBE_ID = 0xB124
WM_HOTKEY = 0x0312
WM_APP = 0x8000
APP_HOTKEY_STOP = WM_APP + 77
PM_NOREMOVE = 0x0000


def _load_win32():
    """Return ``(user32, kernel32)`` or ``(None, None)`` off Windows."""
    if os.name != "nt":
        return None, None
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.RegisterHotKey.argtypes = [
        wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT
    ]
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.PeekMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
        wintypes.UINT, wintypes.UINT,
    ]
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
    ]
    user32.PostThreadMessageW.argtypes = [
        wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    ]
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    return user32, kernel32


class GlobalHotkeyListener:
    """Registers one hotkey and invokes ``on_press`` when it fires."""

    def __init__(self, hotkey_id: str, on_press: Callable[[], None]) -> None:
        self.hotkey_id = hotkey_id
        self._on_press = on_press
        self._user32, self._kernel32 = _load_win32()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self.registered = False
        self.active_label = hotkey_id

    def start(self, timeout: float = 2.0) -> bool:
        """Start the listener thread. Returns whether registration succeeded."""
        if self._user32 is None:
            return False
        self._thread = threading.Thread(
            target=self._run, name="ResourceHubHotkey", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout)
        return self.registered

    def _run(self) -> None:
        msg = wintypes.MSG()
        # Force creation of this thread's message queue before registering.
        self._user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
        self._thread_id = self._kernel32.GetCurrentThreadId()

        parsed = parse_hotkey_id(self.hotkey_id)
        if parsed:
            label, modifiers, vk = parsed
            self.registered = bool(
                self._user32.RegisterHotKey(None, APP_HOTKEY_ID, modifiers, vk)
            )
            if self.registered:
                self.active_label = label
        self._ready.set()
        if not self.registered:
            return
        try:
            while True:
                result = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result <= 0:
                    break
                if msg.message == WM_HOTKEY and msg.wParam == APP_HOTKEY_ID:
                    try:
                        self._on_press()
                    except Exception:
                        # A failing callback must not kill the message pump.
                        pass
                elif msg.message == APP_HOTKEY_STOP:
                    break
        finally:
            try:
                self._user32.UnregisterHotKey(None, APP_HOTKEY_ID)
            except Exception:
                pass
            self.registered = False

    def stop(self, timeout: float = 2.0) -> None:
        if self._user32 is None:
            return
        if self._thread_id:
            self._user32.PostThreadMessageW(self._thread_id, APP_HOTKEY_STOP, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def __enter__(self) -> GlobalHotkeyListener:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()


def is_combination_available(hotkey_id: str) -> bool:
    """Check whether a hotkey combination can be registered right now.

    Mirrors the legacy pre-save probe (``resource_hub.pyw:1068-1083``): register
    under a temporary id, then release immediately. Returns ``False`` when the
    combination is taken by another process or cannot be parsed.
    """
    user32, _kernel32 = _load_win32()
    if user32 is None:
        return False
    parsed = parse_hotkey_id(hotkey_id)
    if not parsed:
        return False
    _label, modifiers, vk = parsed
    acquired = bool(user32.RegisterHotKey(None, APP_HOTKEY_PROBE_ID, modifiers, vk))
    if acquired:
        user32.UnregisterHotKey(None, APP_HOTKEY_PROBE_ID)
    return acquired
