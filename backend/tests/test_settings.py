"""Tests for settings normalisation and persistence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from resource_hub_core.settings import (
    DEFAULT_HOTKEY_ID,
    DEFAULT_LANGUAGE,
    DEFAULT_QUICK_FOLDERS_HOTKEY_ID,
    DEFAULT_QUICK_LINKS_HOTKEY_ID,
    Settings,
    SettingsStore,
)


class SettingsNormalizeTests(unittest.TestCase):
    def test_quick_panel_defaults(self) -> None:
        settings = Settings()
        # Four-key combinations: Ctrl+Alt+L/F are already claimed by other apps
        # on the reference machine, so plain L/F would be unavailable there.
        self.assertEqual(DEFAULT_QUICK_LINKS_HOTKEY_ID, "Ctrl + Alt + Shift + L")
        self.assertEqual(DEFAULT_QUICK_FOLDERS_HOTKEY_ID, "Ctrl + Alt + Shift + F")
        self.assertEqual(settings.quick_links_hotkey_id, DEFAULT_QUICK_LINKS_HOTKEY_ID)
        self.assertEqual(settings.quick_folders_hotkey_id, DEFAULT_QUICK_FOLDERS_HOTKEY_ID)

    def test_defaults_for_non_mapping(self) -> None:
        for raw in (None, [], "x", 42):
            with self.subTest(raw=raw):
                settings = Settings.normalize(raw)
                self.assertEqual(settings.language, DEFAULT_LANGUAGE)
                self.assertEqual(settings.global_hotkey_id, DEFAULT_HOTKEY_ID)
                self.assertEqual(
                    settings.quick_links_hotkey_id, DEFAULT_QUICK_LINKS_HOTKEY_ID
                )
                self.assertEqual(
                    settings.quick_folders_hotkey_id, DEFAULT_QUICK_FOLDERS_HOTKEY_ID
                )
                self.assertTrue(settings.global_hotkey_enabled)
                self.assertFalse(settings.launch_at_startup)

    def test_invalid_language_falls_back(self) -> None:
        self.assertEqual(Settings.normalize({"language": "fr"}).language, DEFAULT_LANGUAGE)

    def test_valid_language_kept(self) -> None:
        self.assertEqual(Settings.normalize({"language": "en"}).language, "en")

    def test_hotkey_is_canonicalised(self) -> None:
        settings = Settings.normalize({"globalHotkeyId": "control+shift+q"})
        self.assertEqual(settings.global_hotkey_id, "Ctrl + Shift + Q")

    def test_invalid_hotkey_keeps_default(self) -> None:
        for value in ("Space", "Ctrl + Nope", "", "Ctrl + A + B"):
            with self.subTest(value=value):
                settings = Settings.normalize({"globalHotkeyId": value})
                self.assertEqual(settings.global_hotkey_id, DEFAULT_HOTKEY_ID)

    def test_quick_panel_hotkeys_are_canonicalised(self) -> None:
        settings = Settings.normalize(
            {
                "quickLinksHotkeyId": "control+shift+l",
                "quickFoldersHotkeyId": "alt+control+f",
            }
        )
        self.assertEqual(settings.quick_links_hotkey_id, "Ctrl + Shift + L")
        self.assertEqual(settings.quick_folders_hotkey_id, "Ctrl + Alt + F")

    def test_invalid_quick_panel_hotkeys_keep_defaults(self) -> None:
        for value in ("Space", "Ctrl + Nope", "", "Ctrl + A + B"):
            with self.subTest(value=value):
                settings = Settings.normalize(
                    {
                        "quickLinksHotkeyId": value,
                        "quickFoldersHotkeyId": value,
                    }
                )
                self.assertEqual(
                    settings.quick_links_hotkey_id, DEFAULT_QUICK_LINKS_HOTKEY_ID
                )
                self.assertEqual(
                    settings.quick_folders_hotkey_id, DEFAULT_QUICK_FOLDERS_HOTKEY_ID
                )

    def test_to_json_normalize_roundtrip_includes_quick_panel_keys(self) -> None:
        payload = Settings().to_json()
        self.assertEqual(
            payload["quickLinksHotkeyId"], DEFAULT_QUICK_LINKS_HOTKEY_ID
        )
        self.assertEqual(
            payload["quickFoldersHotkeyId"], DEFAULT_QUICK_FOLDERS_HOTKEY_ID
        )
        self.assertEqual(Settings.normalize(payload), Settings())

    def test_non_bool_flags_are_ignored(self) -> None:
        settings = Settings.normalize(
            {"globalHotkeyEnabled": "yes", "launchAtStartup": 1}
        )
        self.assertTrue(settings.global_hotkey_enabled)
        self.assertFalse(settings.launch_at_startup)

    def test_bool_flags_are_honoured(self) -> None:
        settings = Settings.normalize(
            {"globalHotkeyEnabled": False, "launchAtStartup": True}
        )
        self.assertFalse(settings.global_hotkey_enabled)
        self.assertTrue(settings.launch_at_startup)


class SettingsStoreTests(unittest.TestCase):
    def test_load_without_file_returns_defaults_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            store = SettingsStore(path)
            self.assertEqual(store.load(), Settings())
            self.assertFalse(path.exists())

    def test_ensure_exists_persists_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            store = SettingsStore(path)
            self.assertEqual(store.ensure_exists(), Settings())
            self.assertTrue(path.exists())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["language"], DEFAULT_LANGUAGE)
            self.assertEqual(payload["globalHotkeyId"], DEFAULT_HOTKEY_ID)
            self.assertEqual(
                payload["quickLinksHotkeyId"], DEFAULT_QUICK_LINKS_HOTKEY_ID
            )
            self.assertEqual(
                payload["quickFoldersHotkeyId"], DEFAULT_QUICK_FOLDERS_HOTKEY_ID
            )

    def test_save_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            store = SettingsStore(path)
            original = Settings(
                language="en",
                global_hotkey_enabled=False,
                global_hotkey_id="Ctrl + Space",
                quick_links_hotkey_id="Ctrl + Shift + L",
                quick_folders_hotkey_id="Ctrl + Shift + F",
                launch_at_startup=True,
            )
            store.save(original)
            self.assertEqual(store.load(), original)

    def test_hand_edited_file_never_breaks_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"language": "de", "globalHotkeyId": "bogus"}', encoding="utf-8")
            settings = SettingsStore(path).load()
            self.assertEqual(settings.language, DEFAULT_LANGUAGE)
            self.assertEqual(settings.global_hotkey_id, DEFAULT_HOTKEY_ID)

    def test_corrupt_file_falls_back_to_defaults_and_is_left_untouched(self) -> None:
        """A broken settings.json must not brick startup (found while packaging)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            broken = b"\xef\xbb\xbf{ this is not json"
            path.write_bytes(broken)

            settings = SettingsStore(path).load()

            self.assertEqual(settings, Settings())
            self.assertEqual(path.read_bytes(), broken)


if __name__ == "__main__":
    unittest.main()
