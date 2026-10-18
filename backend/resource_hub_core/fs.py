"""Read-only filesystem browsing for the folder preview panel (Phase 9).

The preview panel lets the user walk a folder resource one level at a time and
open a discovered folder/file in Explorer. Nothing here mutates the resource
data; writes stay in :mod:`resource_hub_core.service`.

Design notes:

* A single listing reads one level only; the UI expands lazily, so a deep tree
  never becomes one huge syscall.
* Entries are sorted folders-first, then by name (casefold) so the tree order is
  stable across machines.
* At most :data:`MAX_ENTRIES` entries are returned, but the whole directory is
  counted (up to :data:`MAX_SCAN` scanned entries) so the UI can say
  "还有 N 项未显示".
* Junctions/symlinks are reported with ``is_link`` and treated as their target
  type; the client guards recursion by depth + ancestor path.
* A missing path, a file passed as a directory, or an unreadable directory
  raises :class:`FsError` with an i18n key the UI can translate.
"""

from __future__ import annotations

import os
import stat as stat_module
from dataclasses import dataclass
from pathlib import Path

from .launcher import open_path, reveal_path
from .service import ServiceError

#: How many children one `fs.children` call returns.
MAX_ENTRIES = 200

#: How many directory entries are scanned/counted (limits huge directories).
MAX_SCAN = 2000


class FsError(ServiceError):
    """A path could not be listed or opened.

    ``key`` is one of ``fs_not_found`` / ``fs_not_directory`` /
    ``fs_permission_denied`` / ``fs_unreadable`` so the Flutter panel can show a
    localized inline message instead of a raw traceback.
    """


@dataclass(frozen=True, slots=True)
class FsEntry:
    """One child of a listed directory."""

    name: str
    path: str

    #: ``"folder"`` or ``"file"``. Links report the type of their target.
    kind: str

    #: True for symlinks / Windows reparse points (junctions included).
    is_link: bool = False

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "isLink": self.is_link,
        }


@dataclass(frozen=True, slots=True)
class FsListing:
    """One directory level, already sorted and capped."""

    path: str
    entries: tuple[FsEntry, ...]
    total: int

    @property
    def shown(self) -> int:
        return len(self.entries)

    @property
    def truncated(self) -> bool:
        return self.total > self.shown


def _is_link(entry: os.DirEntry[str]) -> bool:
    try:
        if entry.is_symlink():
            return True
    except OSError:
        return False
    try:
        info = entry.stat(follow_symlinks=False)
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)


def _resolve_existing(raw_path: str) -> Path:
    text = str(raw_path or "").strip()
    if not text:
        raise FsError("fs_not_found", "empty path")
    path = Path(text)
    try:
        path.stat()
    except FileNotFoundError as exc:
        raise FsError("fs_not_found", text) from exc
    except PermissionError as exc:
        raise FsError("fs_permission_denied", text) from exc
    except OSError as exc:
        raise FsError("fs_unreadable", f"{text}: {exc}") from exc
    return path


def list_children(raw_path: str) -> FsListing:
    """List one directory level, sorted folders-first then by name."""
    path = _resolve_existing(raw_path)
    try:
        is_dir = path.is_dir()
    except OSError as exc:
        raise FsError("fs_unreadable", f"{path}: {exc}") from exc
    if not is_dir:
        raise FsError("fs_not_directory", str(path))

    entries: list[FsEntry] = []
    total = 0
    try:
        with os.scandir(path) as scan:
            for entry in scan:
                total += 1
                if len(entries) >= MAX_SCAN:
                    continue
                try:
                    is_folder = entry.is_dir()
                except OSError:
                    is_folder = False
                entries.append(
                    FsEntry(
                        name=entry.name,
                        path=entry.path,
                        kind="folder" if is_folder else "file",
                        is_link=_is_link(entry),
                    )
                )
    except PermissionError as exc:
        raise FsError("fs_permission_denied", str(path)) from exc
    except OSError as exc:
        raise FsError("fs_unreadable", f"{path}: {exc}") from exc

    entries.sort(key=lambda item: (0 if item.kind == "folder" else 1, item.name.casefold()))
    shown = tuple(entries[:MAX_ENTRIES])
    return FsListing(path=str(path), entries=shown, total=total)


def open_fs_path(raw_path: str) -> None:
    """Open a discovered folder/file with the shell; read-only operation."""
    path = _resolve_existing(raw_path)
    open_path(str(path))


def reveal_fs_path(raw_path: str) -> None:
    """Show a discovered folder/file in Explorer; read-only operation."""
    path = _resolve_existing(raw_path)
    reveal_path(str(path))
