"""Windows-only checks for the global hotkey listener.

Registration depends on the machine (another app may own the combination), so
these tests skip rather than fail when the combination is unavailable. The
authoritative end-to-end check — including WM_HOTKEY delivery under simulated
key presses — is ``migration/probes/probe_headless_tray_hotkey.py``.
"""

from __future__ import annotations

import os
import unittest

from resource_hub_core.hotkey import GlobalHotkeyListener, is_combination_available

# Unlikely to be taken by another application.
PROBE_HOTKEY = "Ctrl + Alt + Shift + F12"


@unittest.skipUnless(os.name == "nt", "global hotkeys are Windows-only")
class HotkeyListenerTests(unittest.TestCase):
    def test_register_then_release_then_reacquire(self) -> None:
        listener = GlobalHotkeyListener(PROBE_HOTKEY, lambda: None)
        if not listener.start():
            self.skipTest(f"{PROBE_HOTKEY} is already taken on this machine")
        try:
            self.assertTrue(listener.registered)
            self.assertEqual(listener.active_label, PROBE_HOTKEY)
        finally:
            listener.stop()
        self.assertFalse(listener.registered)

        # Releasing must be complete: the same combination is immediately free.
        again = GlobalHotkeyListener(PROBE_HOTKEY, lambda: None)
        try:
            self.assertTrue(again.start())
        finally:
            again.stop()

    def test_callback_errors_do_not_kill_the_pump(self) -> None:
        # The handler is invoked on the message thread; an exception there must be
        # swallowed so the pump keeps running.
        def boom() -> None:
            raise RuntimeError("callback failed")

        listener = GlobalHotkeyListener(PROBE_HOTKEY, boom)
        if not listener.start():
            self.skipTest(f"{PROBE_HOTKEY} is already taken on this machine")
        try:
            self.assertTrue(listener.registered)
        finally:
            listener.stop()

    def test_invalid_combination_is_reported_unavailable(self) -> None:
        for value in ("", "Space", "Ctrl + Nope"):
            with self.subTest(value=value):
                self.assertFalse(is_combination_available(value))


if __name__ == "__main__":
    unittest.main()
