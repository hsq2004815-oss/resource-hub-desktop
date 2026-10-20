"""Global mouse side-button listener — Windows only, stdlib ctypes.

XBUTTON1 / XBUTTON2 ("back" / "forward") open the two quick panels. The hook
swallows those two events on purpose: leaving them through would navigate the
browser back/forward while the panel opens.

``WH_MOUSE_LL`` is delivered to the thread that installed the hook, so this owns
a thread + message pump exactly like :mod:`resource_hub_core.hotkey`.
"""

from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes
from typing import Callable

WH_MOUSE_LL = 14
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002
#: High word of ``MSLLHOOKSTRUCT.mouseData`` → quick-panel action.
SIDE_BUTTON_ACTIONS = {XBUTTON1: "quickLinks", XBUTTON2: "quickFolders"}

WM_APP = 0x8000
APP_MOUSE_STOP = WM_APP + 78
PM_NOREMOVE = 0x0000


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


#: LRESULT CALLBACK LowLevelMouseProc(int, WPARAM, LPARAM)
_HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


def _load_win32():
    """Return ``(user32, kernel32)`` or ``(None, None)`` off Windows."""
    if os.name != "nt":
        return None, None
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD
    ]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    user32.CallNextHookEx.argtypes = [
        wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
    ]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
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


def _button(mouse_data: int) -> int | None:
    """The XBUTTON id packed in the high word of ``mouseData``."""
    button = (mouse_data >> 16) & 0xFFFF
    return button if button in SIDE_BUTTON_ACTIONS else None


def side_button_action(message: int, mouse_data: int) -> str | None:
    """Quick-panel action for an XBUTTON-down message, or ``None``."""
    if message != WM_XBUTTONDOWN:
        return None
    button = _button(mouse_data)
    return SIDE_BUTTON_ACTIONS[button] if button is not None else None


def swallows_side_button(message: int, mouse_data: int) -> bool:
    """Whether this hook call must be swallowed (down *and* up of both buttons)."""
    return message in (WM_XBUTTONDOWN, WM_XBUTTONUP) and _button(mouse_data) is not None


class MouseSideButtonListener:
    """Installs the low-level mouse hook and reports side-button presses."""

    def __init__(self, on_action: Callable[[str], None]) -> None:
        self._on_action = on_action
        self._user32, self._kernel32 = _load_win32()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._hook = None
        #: Kept alive on the instance: a collected ctypes callback would be
        #: freed while Windows still holds the function pointer.
        self._proc = None
        self.registered = False

    def start(self, timeout: float = 2.0) -> bool:
        """Start the hook thread. Returns whether the hook was installed."""
        if self._user32 is None:
            return False
        self._thread = threading.Thread(
            target=self._run, name="ResourceHubMouseHook", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout)
        return self.registered

    def _run(self) -> None:
        user32 = self._user32
        msg = wintypes.MSG()
        # Force this thread's message queue before installing the hook.
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
        self._thread_id = self._kernel32.GetCurrentThreadId()
        self._proc = _HOOKPROC(self._hook_proc)
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)
        self.registered = bool(self._hook)
        self._ready.set()
        if not self.registered:
            return
        try:
            while True:
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result <= 0 or msg.message == APP_MOUSE_STOP:
                    break
        finally:
            try:
                user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
            self._hook = None
            self.registered = False

    def _hook_proc(self, n_code, w_param, l_param):
        """Low-level hook callback: fast, no I/O, never raises."""
        if n_code >= 0:
            info = MSLLHOOKSTRUCT.from_address(l_param)
            try:
                action = side_button_action(w_param, info.mouseData)
                if action is not None:
                    self._on_action(action)
                if swallows_side_button(w_param, info.mouseData):
                    return 1
            except Exception:
                # A failing callback must not break the hook chain.
                pass
        return self._user32.CallNextHookEx(None, n_code, w_param, l_param)

    def stop(self, timeout: float = 2.0) -> None:
        if self._user32 is None:
            return
        if self._thread_id:
            self._user32.PostThreadMessageW(self._thread_id, APP_MOUSE_STOP, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def __enter__(self) -> MouseSideButtonListener:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()
