"""``settings.json`` model and store.

Mirrors ``_normalize_settings`` (``resource_hub.pyw:1829``): unknown or invalid
values fall back to defaults rather than raising, so a hand-edited settings file
can never brick the app.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .normalize import parse_hotkey_id
from .storage import CorruptDataError, JsonFileStore

DEFAULT_LANGUAGE = "zh"
DEFAULT_HOTKEY_ID = "Ctrl + Alt + Space"
DEFAULT_QUICK_LINKS_HOTKEY_ID = "Ctrl + Alt + Shift + L"
DEFAULT_QUICK_FOLDERS_HOTKEY_ID = "Ctrl + Alt + Shift + F"
SUPPORTED_LANGUAGES = frozenset({"zh", "en"})


@dataclass(frozen=True, slots=True)
class Settings:
    language: str = DEFAULT_LANGUAGE
    global_hotkey_enabled: bool = True
    global_hotkey_id: str = DEFAULT_HOTKEY_ID
    quick_links_hotkey_id: str = DEFAULT_QUICK_LINKS_HOTKEY_ID
    quick_folders_hotkey_id: str = DEFAULT_QUICK_FOLDERS_HOTKEY_ID
    launch_at_startup: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "globalHotkeyEnabled": self.global_hotkey_enabled,
            "globalHotkeyId": self.global_hotkey_id,
            "quickLinksHotkeyId": self.quick_links_hotkey_id,
            "quickFoldersHotkeyId": self.quick_folders_hotkey_id,
            "launchAtStartup": self.launch_at_startup,
        }

    @classmethod
    def normalize(cls, raw: Any) -> Settings:
        settings = cls()
        if not isinstance(raw, Mapping):
            return settings

        language = raw.get("language")
        if language in SUPPORTED_LANGUAGES:
            settings = replace(settings, language=str(language))

        enabled = raw.get("globalHotkeyEnabled")
        if isinstance(enabled, bool):
            settings = replace(settings, global_hotkey_enabled=enabled)

        hotkey_id = raw.get("globalHotkeyId")
        parsed = parse_hotkey_id(str(hotkey_id)) if hotkey_id is not None else None
        if parsed:
            settings = replace(settings, global_hotkey_id=parsed[0])

        quick_links_id = raw.get("quickLinksHotkeyId")
        parsed = (
            parse_hotkey_id(str(quick_links_id))
            if quick_links_id is not None
            else None
        )
        if parsed:
            settings = replace(settings, quick_links_hotkey_id=parsed[0])

        quick_folders_id = raw.get("quickFoldersHotkeyId")
        parsed = (
            parse_hotkey_id(str(quick_folders_id))
            if quick_folders_id is not None
            else None
        )
        if parsed:
            settings = replace(settings, quick_folders_hotkey_id=parsed[0])

        startup = raw.get("launchAtStartup")
        if isinstance(startup, bool):
            settings = replace(settings, launch_at_startup=startup)

        return settings


class SettingsStore:
    """Loads and saves ``settings.json`` next to the executable."""

    def __init__(self, path: Path) -> None:
        self._store = JsonFileStore(path)

    @property
    def path(self) -> Path:
        return self._store.path

    def load(self) -> Settings:
        """Return current settings; defaults when the file is absent or unreadable.

        A corrupt ``settings.json`` must never stop the backend from starting:
        unlike ``sites.json`` / ``folders.json`` (which have an explicit
        read-only corrupt mode) settings only carry preferences, so falling back
        to defaults is safe. The broken file is left untouched for manual repair
        — this is the contract promised by the module docstring.

        Note: a UTF-8 BOM is *not* valid JSON for :mod:`json`; a hand-edited
        file saved as "UTF-8 with BOM" lands here (found while packaging).
        """
        try:
            raw = self._store.load_or_none()
        except CorruptDataError:
            return Settings()
        return Settings.normalize(raw)

    def ensure_exists(self) -> Settings:
        """Persist defaults when the file is missing (first run)."""
        if not self.path.exists():
            settings = Settings()
            self.save(settings)
            return settings
        return self.load()

    def save(self, settings: Settings) -> None:
        self._store.save(settings.to_json())
