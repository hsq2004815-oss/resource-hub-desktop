"""Installed browsers for the per-site "open with" choice (Windows).

The list comes from the shell's ``StartMenuInternet`` registry keys, which Chrome,
Edge and most other browsers register when installed. Stored per site as the
browser id (``chrome`` / ``edge`` / …); the executable path is resolved again at
open time so a reinstall or move still works.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

CHROME = "chrome"
EDGE = "edge"

#: exe file name → stable id. Unknown browsers fall back to the exe stem.
_KNOWN_IDS = {
    "chrome.exe": CHROME,
    "msedge.exe": EDGE,
    "firefox.exe": "firefox",
    "brave.exe": "brave",
    "opera.exe": "opera",
    "vivaldi.exe": "vivaldi",
    "360se.exe": "360se",
    "360chrome.exe": "360chrome",
    "qqbrowser.exe": "qqbrowser",
    "sogouexplorer.exe": "sogou",
}

#: Bookmark profile label prefix → browser id (imported sites remember origin).
_LABEL_IDS = {"chrome": CHROME, "edge": EDGE}


@dataclass(frozen=True, slots=True)
class Browser:
    """One installed browser: stable id, display name, executable path."""

    id: str
    name: str
    command: str

    def to_json(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "path": self.command}


def exe_from_command(command: str) -> str | None:
    """The executable path in a shell ``open\\command`` string."""
    text = command.strip()
    if not text:
        return None
    if text.startswith('"'):
        end = text.find('"', 1)
        return text[1:end] or None if end > 1 else None
    # Some registrations leave the path unquoted even when it contains spaces
    # (Edge, Internet Explorer); cut at the first ".exe" instead of the first
    # space, otherwise "C:\Program Files\..." becomes the browser "program".
    exe_end = text.casefold().find(".exe")
    if exe_end != -1:
        return text[: exe_end + 4].strip()
    return text.split(" ", 1)[0] or None


def browser_id_for(exe: str) -> str:
    """Stable id for an executable path (``…\\msedge.exe`` → ``edge``)."""
    name = os.path.basename(exe).strip().casefold()
    return _KNOWN_IDS.get(name) or os.path.splitext(name)[0]


def browser_id_for_label(label: str) -> str:
    """Bookmark profile label → browser id (``Chrome · Default`` → ``chrome``)."""
    prefix = label.split(" · ", 1)[0].strip().casefold()
    return _LABEL_IDS.get(prefix, "")


def _registry_entries() -> list[tuple[str, str]]:
    """``(display name, open command)`` pairs from HKCU/HKLM, best effort."""
    if os.name != "nt":
        return []
    import winreg

    entries: list[tuple[str, str]] = []
    key_path = r"SOFTWARE\Clients\StartMenuInternet"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            clients = winreg.OpenKey(root, key_path)
        except OSError:
            continue
        with clients:
            index = 0
            while True:
                try:
                    sub = winreg.EnumKey(clients, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(clients, sub) as client:
                        name = str(winreg.QueryValueEx(client, "")[0] or sub)
                    with winreg.OpenKey(
                        clients, sub + r"\shell\open\command"
                    ) as command_key:
                        command = str(winreg.QueryValueEx(command_key, "")[0])
                except OSError:
                    continue
                entries.append((name, command))
    return entries


def installed_browsers() -> list[Browser]:
    """Installed browsers, deduplicated by id and sorted by display name."""
    found: dict[str, Browser] = {}
    for name, command in _registry_entries():
        exe = exe_from_command(command)
        if not exe:
            continue
        browser_id = browser_id_for(exe)
        if browser_id in found or browser_id == "iexplore":
            # Legacy IE registers itself but cannot open modern sites.
            continue
        found[browser_id] = Browser(browser_id, name, exe)
    return sorted(found.values(), key=lambda browser: browser.name.casefold())


def find_browser(browser_id: str) -> Browser | None:
    """The installed browser with this id, or ``None`` when it is gone."""
    target = (browser_id or "").strip().casefold()
    if not target:
        return None
    for browser in installed_browsers():
        if browser.id == target:
            return browser
    return None
