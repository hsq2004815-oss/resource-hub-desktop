"""Programs that can open a folder or a file (Phase 34).

A fixed preset list, probed on this machine, exposed as "openers.list" and
referenced by id from a resource's "openWith" field. Mirrors browsers.py:
an unknown id never runs anything, it falls back to the system default.

Why a preset list instead of "any exe": the id is stored in folders.json and
replayed on double-click, so it must never be able to point at an arbitrary
program that a hand-edited file could inject.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

#: How the launcher should start the program.
KIND_SYSTEM = "system"
KIND_EDITOR = "editor"
KIND_TERMINAL = "terminal"


@dataclass(frozen=True)
class Opener:
    id: str
    name: str
    #: Resolved executable; empty for the system default.
    command: str = ""
    kind: str = KIND_SYSTEM

    @property
    def available(self) -> bool:
        return self.kind == KIND_SYSTEM or bool(self.command)

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "available": self.available,
        }


def _env_dir(name: str) -> str:
    return os.environ.get(name, "") or ""


def _uninstall_exe(needle: str) -> str:
    """Executable of an app whose uninstall entry name contains needle.

    VS Code happily installs to a custom directory (this machine keeps it in
    "E:\\ VS Code"), so hard-coded paths are only the fast path; the
    uninstall entry is the reliable one.
    """
    if os.name != "nt":
        return ""
    import winreg

    base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                uninstall = winreg.OpenKey(root, base, 0, winreg.KEY_READ | view)
            except OSError:
                continue
            with uninstall:
                index = 0
                while True:
                    try:
                        sub = winreg.EnumKey(uninstall, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(uninstall, sub) as entry:
                            name = str(winreg.QueryValueEx(entry, "DisplayName")[0])
                            if needle.casefold() not in name.casefold():
                                continue
                            try:
                                location = str(
                                    winreg.QueryValueEx(entry, "InstallLocation")[0]
                                ).strip()
                            except OSError:
                                location = ""
                    except OSError:
                        continue
                    if location:
                        candidate = Path(location) / "Code.exe"
                        try:
                            if candidate.is_file():
                                return str(candidate)
                        except OSError:
                            pass
    return ""

def _vscode() -> str:
    """Where VS Code landed: user install, system install, or a custom folder."""
    candidates = [
        Path(_env_dir("LOCALAPPDATA")) / "Programs" / "Microsoft VS Code" / "Code.exe",
        Path(_env_dir("PROGRAMFILES")) / "Microsoft VS Code" / "Code.exe",
        Path(_env_dir("PROGRAMFILES(X86)")) / "Microsoft VS Code" / "Code.exe",
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    # A custom install location is common; ask the uninstall entry.
    return _uninstall_exe("Visual Studio Code")


def _terminal() -> str:
    # Store-app alias; only resolvable when WindowsApps is on PATH.
    return shutil.which("wt.exe") or shutil.which("wt") or ""


def _powershell() -> str:
    return shutil.which("powershell.exe") or shutil.which("powershell") or ""


def _cmd() -> str:
    return _env_dir("COMSPEC") or shutil.which("cmd.exe") or shutil.which("cmd") or ""


def installed_openers() -> list[Opener]:
    """Every preset, with "available" telling the UI which to offer."""
    return [
        Opener("system", "System default", "", KIND_SYSTEM),
        Opener("vscode", "Visual Studio Code", _vscode(), KIND_EDITOR),
        Opener("wt", "Windows Terminal", _terminal(), KIND_TERMINAL),
        Opener("powershell", "PowerShell", _powershell(), KIND_TERMINAL),
        Opener("cmd", "Command Prompt", _cmd(), KIND_TERMINAL),
    ]


def find_opener(opener_id: str) -> Opener | None:
    """The preset for opener_id; None when unknown or not installed."""
    wanted = (opener_id or "").strip().lower()
    if not wanted:
        return None
    for opener in installed_openers():
        if opener.id == wanted and opener.available:
            return opener
    return None
