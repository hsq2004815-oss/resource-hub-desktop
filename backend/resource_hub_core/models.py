"""Domain models for the two datasets, mirroring the legacy JSON contract.

``sites.json`` entries use ``url``; ``folders.json`` entries use ``path`` plus
``kind``. Both carry ``id / name / category / note / favorite / createdAt``.

Normalisation is a direct port of ``_normalize_site`` / ``_normalize_folder``
(``resource_hub.pyw:1914-1948``) so existing data files keep loading unchanged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from .normalize import normalize_folder_path, normalize_url, now_iso

#: Stored when the user picks no category. Never shown to the user as-is.
UNCATEGORIZED = "__uncategorized__"

#: In-memory filter sentinel for "all categories". Never persisted.
ALL_CATEGORIES = "__all__"

#: Legacy values that also mean "uncategorised" when read from disk.
_UNCATEGORIZED_ALIASES = frozenset({"Uncategorized", "未分类"})

MODES: tuple[str, str] = ("links", "folders")


def normalize_category(raw: Any) -> str:
    category = str(raw or "").strip()
    if not category or category in _UNCATEGORIZED_ALIASES:
        return UNCATEGORIZED
    return category


@runtime_checkable
class Resource(Protocol):
    """What the service needs from either dataset entry."""

    id: str
    name: str
    category: str
    note: str
    favorite: bool
    created_at: str

    @property
    def target(self) -> str:
        """The URL (links) or filesystem path (folders)."""

    def to_json(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Site:
    id: str
    name: str
    url: str
    category: str = UNCATEGORIZED
    note: str = ""
    favorite: bool = False
    created_at: str = ""
    #: Browser id used to open this site (``chrome`` / ``edge`` / …); empty means
    #: the system default browser. Imported bookmarks keep their origin.
    browser: str = ""

    @property
    def target(self) -> str:
        return self.url

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "category": self.category,
            "note": self.note,
            "favorite": self.favorite,
            "createdAt": self.created_at,
        }
        if self.browser:
            payload["browser"] = self.browser
        return payload

    @classmethod
    def normalize(cls, raw: Mapping[str, Any]) -> Site:
        return cls(
            id=str(raw.get("id") or uuid.uuid4()),
            name=str(raw.get("name") or ""),
            url=normalize_url(str(raw.get("url") or "")),
            category=normalize_category(raw.get("category")),
            note=str(raw.get("note") or ""),
            favorite=bool(raw.get("favorite")),
            created_at=str(raw.get("createdAt") or now_iso()),
            browser=str(raw.get("browser") or "").strip().casefold(),
        )

    @staticmethod
    def is_complete(raw: Mapping[str, Any]) -> bool:
        """Entries missing ``name`` or ``url`` are dropped on load."""
        return bool(raw.get("name")) and bool(raw.get("url"))


@dataclass(frozen=True, slots=True)
class Folder:
    id: str
    name: str
    path: str
    kind: str = "folder"
    category: str = UNCATEGORIZED
    note: str = ""
    favorite: bool = False
    created_at: str = ""

    @property
    def target(self) -> str:
        return self.path

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "category": self.category,
            "note": self.note,
            "favorite": self.favorite,
            "createdAt": self.created_at,
        }

    @classmethod
    def normalize(cls, raw: Mapping[str, Any]) -> Folder:
        # Older files stored the location under `url`; accept both.
        raw_path = raw.get("path") or raw.get("url") or ""
        normalized_path = normalize_folder_path(str(raw_path))

        kind = str(raw.get("kind") or "").lower()
        if kind not in {"file", "folder"}:
            # Net effect of the legacy branch: folder only if it exists and is a dir.
            probe = Path(normalized_path)
            kind = "folder" if probe.exists() and probe.is_dir() else "file"

        return cls(
            id=str(raw.get("id") or uuid.uuid4()),
            name=str(raw.get("name") or ""),
            path=normalized_path,
            kind=kind,
            category=normalize_category(raw.get("category")),
            note=str(raw.get("note") or ""),
            favorite=bool(raw.get("favorite")),
            created_at=str(raw.get("createdAt") or now_iso()),
        )

    @staticmethod
    def is_complete(raw: Mapping[str, Any]) -> bool:
        """Entries missing ``name`` or a location are dropped on load."""
        return bool(raw.get("name")) and bool(raw.get("path") or raw.get("url"))


def parse_entry(mode: str, raw: Mapping[str, Any]) -> Resource:
    """Normalise one raw JSON object for ``mode``."""
    if mode == "links":
        return Site.normalize(raw)
    if mode == "folders":
        return Folder.normalize(raw)
    raise ValueError(f"unknown mode: {mode!r}")


def is_complete(mode: str, raw: Mapping[str, Any]) -> bool:
    if mode == "links":
        return Site.is_complete(raw)
    if mode == "folders":
        return Folder.is_complete(raw)
    raise ValueError(f"unknown mode: {mode!r}")


def with_changes(item: Resource, **changes: Any) -> Resource:
    """Immutable update that keeps the concrete dataclass type."""
    return replace(item, **changes)  # type: ignore[type-var]
