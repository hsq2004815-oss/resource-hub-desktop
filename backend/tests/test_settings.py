"""Tests for settings normalisation and persistence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from resource_hub_core.settings import (
    DEFAULT_AI_BASE_URL,
    DEFAULT_AI_MODEL,
    DEFAULT_BOOKMARK_DELETE_MODE,
    DEFAULT_HOTKEY_ID,
    DEFAULT_LANGUAGE,
    DEFAULT_QUICK_FOLDERS_HOTKEY_ID,
    DEFAULT_QUICK_LINKS_HOTKEY_ID,
    DELETE_MODES,
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
                self.assertTrue(settings.bookmark_sync_enabled)
                self.assertEqual(settings.bookmark_custom_dir, "")
                self.assertEqual(
                    settings.bookmark_delete_mode, DEFAULT_BOOKMARK_DELETE_MODE
                )

    def test_bookmark_defaults(self) -> None:
        settings = Settings()
        self.assertTrue(settings.bookmark_sync_enabled)
        self.assertEqual(settings.bookmark_custom_dir, "")
        self.assertEqual(settings.bookmark_delete_mode, "ask")

    def test_bookmark_delete_mode_defaults_and_values(self) -> None:
        self.assertEqual(DEFAULT_BOOKMARK_DELETE_MODE, "ask")
        self.assertEqual(set(DELETE_MODES), {"ask", "remove", "keep"})
        for value in DELETE_MODES:
            with self.subTest(value=value):
                settings = Settings.normalize({"bookmarkDeleteMode": value})
                self.assertEqual(settings.bookmark_delete_mode, value)

    def test_invalid_bookmark_delete_mode_falls_back_to_ask(self) -> None:
        for value in (None, "", "   ", "delete", "REMOVE", 42, True, ["remove"]):
            with self.subTest(value=value):
                settings = Settings.normalize({"bookmarkDeleteMode": value})
                self.assertEqual(settings.bookmark_delete_mode, "ask")

    def test_bookmark_settings_are_normalised(self) -> None:
        settings = Settings.normalize(
            {"bookmarkSyncEnabled": False, "bookmarkCustomDir": "  D:\\Bookmarks  "}
        )
        self.assertFalse(settings.bookmark_sync_enabled)
        self.assertEqual(settings.bookmark_custom_dir, "D:\\Bookmarks")

    def test_blank_bookmark_custom_dir_is_allowed(self) -> None:
        settings = Settings.normalize({"bookmarkCustomDir": "   "})
        self.assertEqual(settings.bookmark_custom_dir, "")

    def test_non_bool_and_non_str_bookmark_values_are_ignored(self) -> None:
        settings = Settings.normalize(
            {"bookmarkSyncEnabled": "yes", "bookmarkCustomDir": 42}
        )
        self.assertTrue(settings.bookmark_sync_enabled)
        self.assertEqual(settings.bookmark_custom_dir, "")

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

    def test_to_json_includes_bookmark_keys(self) -> None:
        payload = Settings(
            bookmark_sync_enabled=False, bookmark_custom_dir="D:\\Bookmarks"
        ).to_json()
        self.assertIs(payload["bookmarkSyncEnabled"], False)
        self.assertEqual(payload["bookmarkCustomDir"], "D:\\Bookmarks")
        self.assertEqual(
            Settings.normalize(payload),
            Settings(bookmark_sync_enabled=False, bookmark_custom_dir="D:\\Bookmarks"),
        )

    def test_to_json_includes_bookmark_delete_mode(self) -> None:
        payload = Settings(bookmark_delete_mode="remove").to_json()
        self.assertEqual(payload["bookmarkDeleteMode"], "remove")
        self.assertEqual(
            Settings.normalize(payload),
            Settings(bookmark_delete_mode="remove"),
        )
        # Every normalized mode survives the write/read round trip.
        for value in DELETE_MODES:
            with self.subTest(value=value):
                payload = Settings(bookmark_delete_mode=value).to_json()
                self.assertEqual(
                    Settings.normalize(payload),
                    Settings(bookmark_delete_mode=value),
                )

    def test_shell_context_menu_setting_round_trip(self) -> None:
        self.assertTrue(Settings().shell_context_menu_enabled)

        payload = Settings(shell_context_menu_enabled=False).to_json()
        self.assertIs(payload["shellContextMenuEnabled"], False)
        self.assertEqual(
            Settings.normalize(payload),
            Settings(shell_context_menu_enabled=False),
        )
        enabled_payload = Settings(shell_context_menu_enabled=True).to_json()
        self.assertEqual(
            Settings.normalize(enabled_payload),
            Settings(shell_context_menu_enabled=True),
        )
        # Non-bool values fall back to the default instead of raising.
        for value in (None, "yes", 0, 1, [], {}):
            with self.subTest(value=value):
                settings = Settings.normalize({"shellContextMenuEnabled": value})
                self.assertTrue(settings.shell_context_menu_enabled)

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

    # -- Phase 22: AI settings --------------------------------------------
    def test_ai_defaults(self) -> None:
        settings = Settings()
        # Opt-in: AI suggestions must stay off until the user enables them.
        self.assertFalse(settings.ai_enabled)
        self.assertEqual(DEFAULT_AI_BASE_URL, "https://api.deepseek.com")
        self.assertEqual(DEFAULT_AI_MODEL, "deepseek-chat")
        self.assertEqual(settings.ai_base_url, DEFAULT_AI_BASE_URL)
        self.assertEqual(settings.ai_model, DEFAULT_AI_MODEL)

    def test_ai_settings_are_normalised(self) -> None:
        settings = Settings.normalize(
            {
                "aiEnabled": True,
                "aiBaseUrl": "  https://api.example.com/v1  ",
                "aiModel": "  deepseek-reasoner  ",
            }
        )
        self.assertTrue(settings.ai_enabled)
        self.assertEqual(settings.ai_base_url, "https://api.example.com/v1")
        self.assertEqual(settings.ai_model, "deepseek-reasoner")

    def test_http_ai_base_url_is_allowed(self) -> None:
        # A local OpenAI-compatible gateway may be plain HTTP.
        settings = Settings.normalize({"aiBaseUrl": "http://localhost:8080/v1"})
        self.assertEqual(settings.ai_base_url, "http://localhost:8080/v1")

    def test_ai_base_url_scheme_is_lowercased(self) -> None:
        settings = Settings.normalize({"aiBaseUrl": "HTTPS://API.Example.com/v1"})
        self.assertEqual(settings.ai_base_url, "https://API.Example.com/v1")

    def test_invalid_ai_base_url_falls_back_to_default(self) -> None:
        for value in (
            None,
            "",
            "   ",
            "api.deepseek.com",
            "ftp://example.com",
            "https://",
            "http://",
            "file:///C:/x",
            "https://api example.com",
            "http://[::1",
            42,
            True,
            [],
            {"url": "https://example.com"},
        ):
            with self.subTest(value=value):
                settings = Settings.normalize({"aiBaseUrl": value})
                self.assertEqual(settings.ai_base_url, DEFAULT_AI_BASE_URL)

    def test_invalid_ai_model_falls_back_to_default(self) -> None:
        for value in (None, "", "   ", 42, True, [], {}):
            with self.subTest(value=value):
                settings = Settings.normalize({"aiModel": value})
                self.assertEqual(settings.ai_model, DEFAULT_AI_MODEL)

    def test_non_bool_ai_enabled_is_ignored(self) -> None:
        for value in (None, "yes", 1, 0, [], {}):
            with self.subTest(value=value):
                settings = Settings.normalize({"aiEnabled": value})
                self.assertFalse(settings.ai_enabled)
        self.assertTrue(Settings.normalize({"aiEnabled": True}).ai_enabled)
        self.assertFalse(Settings.normalize({"aiEnabled": False}).ai_enabled)

    def test_ai_settings_round_trip(self) -> None:
        original = Settings(
            ai_enabled=True,
            ai_base_url="https://api.example.com/v1",
            ai_model="deepseek-reasoner",
        )
        payload = original.to_json()
        self.assertIs(payload["aiEnabled"], True)
        self.assertEqual(payload["aiBaseUrl"], "https://api.example.com/v1")
        self.assertEqual(payload["aiModel"], "deepseek-reasoner")
        self.assertEqual(Settings.normalize(payload), original)
        # The API key is never a settings field: settings.json stays plain JSON.
        self.assertNotIn("apiKey", payload)
        self.assertNotIn("aiKey", payload)


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
                bookmark_sync_enabled=False,
                bookmark_custom_dir="D:\\Bookmarks",
            )
            store.save(original)
            self.assertEqual(store.load(), original)

    def test_ai_settings_persist_through_settings_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            store = SettingsStore(path)
            original = Settings(
                ai_enabled=True,
                ai_base_url="https://api.example.com/v1",
                ai_model="deepseek-reasoner",
            )
            store.save(original)
            self.assertEqual(store.load(), original)
            # The persisted file is plain JSON, but it holds no key material.
            text = path.read_text(encoding="utf-8")
            self.assertIn('"aiBaseUrl": "https://api.example.com/v1"', text)
            self.assertNotIn("apiKey", text)

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
