"""Tests for the side-button mapping and the swallow rule."""

from __future__ import annotations

import unittest

from resource_hub_core.mousehook import (
    WM_XBUTTONDOWN,
    WM_XBUTTONUP,
    XBUTTON1,
    XBUTTON2,
    side_button_action,
    swallows_side_button,
)

WM_MOUSEMOVE = 0x0200


def xbutton(button: int) -> int:
    """``mouseData`` with ``button`` in its high word, like the hook receives."""
    return button << 16


class SideButtonMappingTests(unittest.TestCase):
    def test_down_maps_back_and_forward(self) -> None:
        self.assertEqual(
            side_button_action(WM_XBUTTONDOWN, xbutton(XBUTTON1)), "quickLinks"
        )
        self.assertEqual(
            side_button_action(WM_XBUTTONDOWN, xbutton(XBUTTON2)), "quickFolders"
        )

    def test_both_buttons_down_and_up_are_swallowed(self) -> None:
        for button in (XBUTTON1, XBUTTON2):
            with self.subTest(button=button):
                data = xbutton(button)
                self.assertTrue(swallows_side_button(WM_XBUTTONDOWN, data))
                self.assertTrue(swallows_side_button(WM_XBUTTONUP, data))
                self.assertIsNone(side_button_action(WM_XBUTTONUP, data))

    def test_unrelated_events_pass_through(self) -> None:
        self.assertIsNone(side_button_action(WM_MOUSEMOVE, xbutton(XBUTTON1)))
        self.assertFalse(swallows_side_button(WM_MOUSEMOVE, 0))
        self.assertFalse(swallows_side_button(WM_XBUTTONDOWN, xbutton(9)))
        self.assertFalse(swallows_side_button(WM_XBUTTONDOWN, 0))


if __name__ == "__main__":
    unittest.main()
