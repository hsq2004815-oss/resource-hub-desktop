"""Tests for the pure helpers ported from resource_hub.pyw (§5.1 of the audit)."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from resource_hub_core.normalize import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    comparable_value,
    format_added,
    normalize_folder_path,
    normalize_url,
    parse_hotkey_id,
)


class NormalizeUrlTests(unittest.TestCase):
    def test_adds_https_when_scheme_missing(self) -> None:
        self.assertEqual(normalize_url("github.com"), "https://github.com")

    def test_keeps_existing_scheme(self) -> None:
        for value in ("https://a.b", "http://a.b", "ftp://a.b"):
            with self.subTest(value=value):
                self.assertEqual(normalize_url(value), value)

    def test_strips_surrounding_whitespace(self) -> None:
        self.assertEqual(normalize_url("  https://a.b  "), "https://a.b")

    def test_empty_input(self) -> None:
        self.assertEqual(normalize_url(""), "")
        self.assertEqual(normalize_url("   "), "")


class NormalizeFolderPathTests(unittest.TestCase):
    def test_expands_environment_variables(self) -> None:
        with mock.patch.dict(os.environ, {"RH_TEST_VAR": r"D:\Sample"}):
            result = normalize_folder_path(r"%RH_TEST_VAR%\sub")
        self.assertEqual(result, os.path.normpath(r"D:\Sample\sub"))

    def test_expands_user_home(self) -> None:
        result = normalize_folder_path("~")
        self.assertEqual(result, os.path.expanduser("~"))

    def test_blank_input_returns_empty(self) -> None:
        self.assertEqual(normalize_folder_path(""), "")
        self.assertEqual(normalize_folder_path("   "), "")


class ComparableValueTests(unittest.TestCase):
    def test_links_ignore_scheme_case_and_trailing_slash(self) -> None:
        self.assertEqual(
            comparable_value("HTTP://A.com/", "links"),
            comparable_value("http://a.com", "links"),
        )

    def test_links_strip_only_one_trailing_slash(self) -> None:
        self.assertEqual(comparable_value("a.com//", "links"), "https://a.com/")

    def test_folders_ignore_case_and_separator(self) -> None:
        self.assertEqual(
            comparable_value(r"D:\Work\App", "folders"),
            comparable_value("d:/work/app/", "folders"),
        )

    def test_empty_folder_path(self) -> None:
        self.assertEqual(comparable_value("   ", "folders"), "")


class ParseHotkeyTests(unittest.TestCase):
    def test_canonical_combination(self) -> None:
        label, modifiers, vk = parse_hotkey_id("Ctrl + Alt + Space")
        self.assertEqual(label, "Ctrl + Alt + Space")
        self.assertEqual(modifiers, MOD_CONTROL | MOD_ALT)
        self.assertEqual(vk, 0x20)

    def test_aliases_are_normalised(self) -> None:
        label, modifiers, vk = parse_hotkey_id("control+shift+q")
        self.assertEqual(label, "Ctrl + Shift + Q")
        self.assertEqual(modifiers, MOD_CONTROL | MOD_SHIFT)
        self.assertEqual(vk, ord("Q"))

    def test_windows_key_alias(self) -> None:
        label, modifiers, _vk = parse_hotkey_id("Super + 1")
        self.assertEqual(label, "Win + 1")
        self.assertEqual(modifiers, MOD_WIN)

    def test_function_keys(self) -> None:
        label, _modifiers, vk = parse_hotkey_id("Alt + F12")
        self.assertEqual(label, "Alt + F12")
        self.assertEqual(vk, 0x70 + 11)

    def test_named_keys(self) -> None:
        for name, expected in (("PageUp", 0x21), ("Backslash", 0xDC), ("Esc", 0x1B)):
            with self.subTest(name=name):
                parsed = parse_hotkey_id(f"Ctrl + {name}")
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed[2], expected)

    def test_invalid_combinations(self) -> None:
        for value in (
            "",
            "Space",            # no modifier
            "Ctrl",             # no key
            "Ctrl + Alt",       # no key
            "Ctrl + A + B",     # two keys
            "Ctrl + Nope",      # unknown key
        ):
            with self.subTest(value=value):
                self.assertIsNone(parse_hotkey_id(value))

    def test_extra_whitespace_tolerated(self) -> None:
        parsed = parse_hotkey_id("  ctrl   +   space ")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed[0], "Ctrl + Space")


class FormatAddedTests(unittest.TestCase):
    def test_iso_with_offset(self) -> None:
        self.assertEqual(format_added("2026-04-22T13:53:49.313959+08:00"), "2026-04-22 13:53")

    def test_garbage_is_returned_unchanged(self) -> None:
        self.assertEqual(format_added("not-a-date"), "not-a-date")

    def test_empty(self) -> None:
        self.assertEqual(format_added(""), "")


if __name__ == "__main__":
    unittest.main()
