"""Tests for the installed-browser helpers (pure parts, no registry)."""

from __future__ import annotations

import unittest

from resource_hub_core.browsers import (
    Browser,
    browser_id_for,
    browser_id_for_label,
    exe_from_command,
)


class CommandParsingTests(unittest.TestCase):
    def test_quoted_command(self) -> None:
        self.assertEqual(
            exe_from_command(
                '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" %1'
            ),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        )

    def test_unquoted_command(self) -> None:
        self.assertEqual(
            exe_from_command("C:\\Browsers\\firefox.exe --url %1"),
            r"C:\Browsers\firefox.exe",
        )

    def test_unquoted_command_with_spaces(self) -> None:
        self.assertEqual(
            exe_from_command(
                "C:\\Program Files (x86)\\Microsoft\\Edge\\Application"
                "\\msedge.exe --single-argument %1"
            ),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        )

    def test_empty_command(self) -> None:
        for value in ("", "   ", '"'):
            with self.subTest(value=value):
                self.assertIsNone(exe_from_command(value))


class BrowserIdTests(unittest.TestCase):
    def test_known_executables(self) -> None:
        self.assertEqual(browser_id_for(r"C:\x\chrome.exe"), "chrome")
        self.assertEqual(browser_id_for(r"C:\x\msedge.exe"), "edge")
        self.assertEqual(browser_id_for(r"C:\x\firefox.exe"), "firefox")

    def test_unknown_executable_uses_the_stem(self) -> None:
        self.assertEqual(browser_id_for(r"C:\x\SomeBrowser.exe"), "somebrowser")

    def test_profile_label_origin(self) -> None:
        self.assertEqual(browser_id_for_label("Chrome · Default"), "chrome")
        self.assertEqual(browser_id_for_label("Edge · Profile 1"), "edge")
        self.assertEqual(browser_id_for_label("自定义 · Default"), "")

    def test_browser_json(self) -> None:
        browser = Browser("chrome", "Google Chrome", r"C:\x\chrome.exe")
        self.assertEqual(
            browser.to_json(),
            {
                "id": "chrome",
                "name": "Google Chrome",
                "path": r"C:\x\chrome.exe",
            },
        )


if __name__ == "__main__":
    unittest.main()
