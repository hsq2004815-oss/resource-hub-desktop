"""Pure normalisation helpers, ported from ``resource_hub.pyw``.

Every function here is side-effect free and UI-free so it can be unit tested
without Tk. Behaviour is copied from the legacy app on purpose — the migration
must not change what users see. Where behaviour *does* change (storage
durability, see ADR-001 D3) the change lives in :mod:`storage`, not here.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

# --- Win32 hotkey constants (resource_hub.pyw:71-91) ------------------------
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
VK_SPACE = 0x20

HOTKEY_MODIFIERS: tuple[tuple[str, int], ...] = (
    ("Ctrl", MOD_CONTROL),
    ("Alt", MOD_ALT),
    ("Shift", MOD_SHIFT),
    ("Win", MOD_WIN),
)

HOTKEY_MODIFIER_ALIASES: dict[str, str] = {
    "CTRL": "Ctrl",
    "CONTROL": "Ctrl",
    "ALT": "Alt",
    "SHIFT": "Shift",
    "WIN": "Win",
    "WINDOWS": "Win",
    "SUPER": "Win",
}

HOTKEY_DISPLAY_TO_VK: dict[str, int] = {
    "Space": VK_SPACE,
    "Tab": 0x09,
    "Enter": 0x0D,
    "Esc": 0x1B,
    "Backspace": 0x08,
    "Delete": 0x2E,
    "Insert": 0x2D,
    "Home": 0x24,
    "End": 0x23,
    "PageUp": 0x21,
    "PageDown": 0x22,
    "Left": 0x25,
    "Up": 0x26,
    "Right": 0x27,
    "Down": 0x28,
    "Minus": 0xBD,
    "Equals": 0xBB,
    "Comma": 0xBC,
    "Period": 0xBE,
    "Slash": 0xBF,
    "Semicolon": 0xBA,
    "Apostrophe": 0xDE,
    "LeftBracket": 0xDB,
    "RightBracket": 0xDD,
    "Backslash": 0xDC,
    "Backtick": 0xC0,
}

HOTKEY_KEY_ALIASES: dict[str, str] = {
    "SPACE": "Space",
    "TAB": "Tab",
    "RETURN": "Enter",
    "ENTER": "Enter",
    "ESC": "Esc",
    "ESCAPE": "Esc",
    "BACKSPACE": "Backspace",
    "BACKSPACEKEY": "Backspace",
    "DELETE": "Delete",
    "DEL": "Delete",
    "INSERT": "Insert",
    "INS": "Insert",
    "HOME": "Home",
    "END": "End",
    "PRIOR": "PageUp",
    "PAGEUP": "PageUp",
    "NEXT": "PageDown",
    "PAGEDOWN": "PageDown",
    "LEFT": "Left",
    "UP": "Up",
    "RIGHT": "Right",
    "DOWN": "Down",
    "MINUS": "Minus",
    "OEM_MINUS": "Minus",
    "EQUAL": "Equals",
    "EQUALS": "Equals",
    "OEM_PLUS": "Equals",
    "COMMA": "Comma",
    "OEM_COMMA": "Comma",
    "PERIOD": "Period",
    "OEM_PERIOD": "Period",
    "SLASH": "Slash",
    "QUESTION": "Slash",
    "OEM_2": "Slash",
    "SEMICOLON": "Semicolon",
    "OEM_1": "Semicolon",
    "APOSTROPHE": "Apostrophe",
    "QUOTERIGHT": "Apostrophe",
    "OEM_7": "Apostrophe",
    "BRACKETLEFT": "LeftBracket",
    "LEFTBRACKET": "LeftBracket",
    "OEM_4": "LeftBracket",
    "BRACKETRIGHT": "RightBracket",
    "RIGHTBRACKET": "RightBracket",
    "OEM_6": "RightBracket",
    "BACKSLASH": "Backslash",
    "OEM_5": "Backslash",
    "GRAVE": "Backtick",
    "ASCIITILDE": "Backtick",
    "QUOTELEFT": "Backtick",
    "OEM_3": "Backtick",
}


def normalize_url(value: str) -> str:
    """Add ``https://`` when the scheme is missing (``resource_hub.pyw:1893``)."""
    value = value.strip()
    if not value:
        return ""
    if "://" in value:
        return value
    return f"https://{value}"


def normalize_folder_path(value: str) -> str:
    """Expand ``%VARS%`` and ``~`` (``resource_hub.pyw:1901``)."""
    if not value.strip():
        return ""
    return str(Path(os.path.expandvars(value.strip())).expanduser())


def comparable_value(value: str, mode: str) -> str:
    """De-duplication key (``resource_hub.pyw:1906``).

    ``mode`` is ``"links"`` or ``"folders"``. Links compare case-insensitively
    with trailing slashes stripped; paths use ``normcase(normpath(...))`` so
    Windows case and separator differences collapse.
    """
    if mode == "links":
        normalized = normalize_url(value).strip().lower()
        return normalized[:-1] if normalized.endswith("/") else normalized
    normalized = normalize_folder_path(value)
    return os.path.normcase(os.path.normpath(normalized)) if normalized else ""


def _normalize_hotkey_key_name(token: str) -> str | None:
    cleaned = str(token).strip()
    if not cleaned:
        return None
    upper = cleaned.upper()
    if upper in HOTKEY_MODIFIER_ALIASES:
        return None
    if upper.startswith("F") and upper[1:].isdigit():
        value = int(upper[1:])
        if 1 <= value <= 24:
            return f"F{value}"
    if len(cleaned) == 1:
        char = cleaned.upper()
        if char.isalpha() or char.isdigit():
            return char
    return HOTKEY_KEY_ALIASES.get(upper)


def parse_hotkey_id(hotkey_id: str) -> tuple[str, int, int] | None:
    """Parse ``"Ctrl + Alt + Space"`` into ``(label, modifiers, vk)``.

    Returns ``None`` for anything invalid: no modifier, no key, two keys, or an
    unknown token (``resource_hub.pyw:224``).
    """
    modifiers = 0
    key_name: str | None = None
    for raw_token in str(hotkey_id).split("+"):
        token = raw_token.strip()
        if not token:
            continue
        modifier_name = HOTKEY_MODIFIER_ALIASES.get(token.upper())
        if modifier_name:
            for label, mask in HOTKEY_MODIFIERS:
                if label == modifier_name:
                    modifiers |= mask
                    break
            continue
        normalized_key = _normalize_hotkey_key_name(token)
        if not normalized_key or key_name is not None:
            return None
        key_name = normalized_key
    if not modifiers or not key_name:
        return None
    if key_name in HOTKEY_DISPLAY_TO_VK:
        vk = HOTKEY_DISPLAY_TO_VK[key_name]
    elif len(key_name) == 1 and key_name.isalpha():
        vk = ord(key_name)
    elif len(key_name) == 1 and key_name.isdigit():
        vk = ord(key_name)
    elif key_name.startswith("F") and key_name[1:].isdigit():
        vk = 0x70 + int(key_name[1:]) - 1
    else:
        return None
    labels = [label for label, mask in HOTKEY_MODIFIERS if modifiers & mask]
    return (" + ".join([*labels, key_name]), modifiers, vk)


def format_added(value: str) -> str:
    """``2026-04-22T13:53:49+08:00`` -> ``2026-04-22 13:53``.

    Unparseable input is returned unchanged (``resource_hub.pyw:2238``).
    """
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return value


def now_iso() -> str:
    """Local-time ISO8601 with offset, matching the legacy ``createdAt`` format."""
    return datetime.now().astimezone().isoformat()
