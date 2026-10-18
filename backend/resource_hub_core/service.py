"""Business layer: all resource operations, with no UI dependency.

This is the code Phase 4 exposes over stdio. Every rule here is a port of the
corresponding method in ``resource_hub.pyw`` — including validation order and
error identity. Errors carry the *legacy translation key* (e.g.
``enter_link_name``) so the Flutter client can render them with the existing
142-key table instead of inventing new messages.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .models import (
    ALL_CATEGORIES,
    UNCATEGORIZED,
    Folder,
    Resource,
    Site,
    is_complete,
    normalize_category,
    parse_entry,
    with_changes,
)
from .normalize import comparable_value, normalize_folder_path, normalize_url, now_iso
from .storage import CorruptDataError, JsonFileStore


# --- errors ----------------------------------------------------------------
class ServiceError(Exception):
    """Base class. ``key`` is a legacy i18n key the client can translate."""

    def __init__(self, key: str, detail: str = "") -> None:
        super().__init__(detail or key)
        self.key = key
        self.detail = detail


class ValidationError(ServiceError):
    """Input failed validation (empty name, bad URL, missing path)."""


class DuplicateError(ServiceError):
    """An entry with the same normalised target already exists."""


class NotFoundError(ServiceError):
    """No entry with the requested id."""


# --- result objects --------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PathCheckResult:
    """Outcome of a path health check."""

    supported: bool
    total: int = 0
    missing: tuple[str, ...] = ()

    @property
    def missing_count(self) -> int:
        return len(self.missing)


@dataclass(frozen=True, slots=True)
class DropResult:
    """Outcome of dropping files/folders onto the window."""

    added: int
    skipped: int
    invalid: int

    @property
    def nothing_added(self) -> bool:
        return self.added == 0


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Outcome of importing a backup file (replaces the collection)."""

    imported: int
    skipped: int


# --- service ---------------------------------------------------------------
class ResourceService:
    """Owns the two collections and their JSON files."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self._stores: dict[str, JsonFileStore] = {
            "links": JsonFileStore(self.base_dir / "sites.json"),
            "folders": JsonFileStore(self.base_dir / "folders.json"),
        }
        self._items: dict[str, list[Resource]] = {"links": [], "folders": []}
        self._loaded = False

    # -- loading -----------------------------------------------------------
    def load(self) -> None:
        """Load both collections.

        Raises :class:`CorruptDataError` if a file exists but cannot be parsed.
        The file is left untouched in that case — see ADR-001 D3.

        An **empty** file is kept empty: sample data is only written when the
        file is absent. The legacy app repopulated samples whenever the list was
        empty, which resurrected deleted entries.
        """
        for mode in ("links", "folders"):
            store = self._stores[mode]
            payload = store.load_or_none()
            if payload is None:
                self._items[mode] = list(self._default_items(mode))
                store.save([item.to_json() for item in self._items[mode]])
                continue
            if not isinstance(payload, list):
                raise CorruptDataError(
                    store.path, f"expected a JSON array, got {type(payload).__name__}"
                )
            self._items[mode] = [
                parse_entry(mode, raw)
                for raw in payload
                if isinstance(raw, Mapping) and is_complete(mode, raw)
            ]
        self._loaded = True

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("ResourceService.load() must be called first")

    def _default_items(self, mode: str) -> tuple[Resource, ...]:
        if mode == "links":
            now = now_iso()
            return (
                Site(id=str(uuid.uuid4()), name="OpenAI", url="https://openai.com/",
                     category="AI", note="Official website", created_at=now),
                Site(id=str(uuid.uuid4()), name="GitHub", url="https://github.com/",
                     category="Development", note="Code hosting and collaboration",
                     created_at=now),
            )
        now = now_iso()
        home = Path.home()
        items: list[Resource] = [
            Folder(id=str(uuid.uuid4()), name=name, path=str(folder), kind="folder",
                   category="System", note="Quick access", created_at=now)
            for name, folder in (
                ("Desktop", home / "Desktop"),
                ("Documents", home / "Documents"),
                ("Downloads", home / "Downloads"),
            )
            if folder.exists()
        ]
        if not items:
            items.append(
                Folder(id=str(uuid.uuid4()), name="App Folder", path=str(self.base_dir),
                       kind="folder", category="System", created_at=now)
            )
        return tuple(items)

    # -- persistence -------------------------------------------------------
    def _save(self, mode: str) -> None:
        self._stores[mode].save([item.to_json() for item in self._items[mode]])

    # -- queries -----------------------------------------------------------
    def items(self, mode: str) -> tuple[Resource, ...]:
        self._require_loaded()
        return tuple(self._items[mode])

    def get(self, mode: str, item_id: str) -> Resource:
        self._require_loaded()
        for item in self._items[mode]:
            if item.id == item_id:
                return item
        raise NotFoundError("select_first_link" if mode == "links" else "select_first_folder",
                            f"no item {item_id!r} in {mode}")

    def categories(self, mode: str) -> tuple[str, ...]:
        """Distinct non-sentinel categories, sorted."""
        self._require_loaded()
        found = {item.category for item in self._items[mode]} - {UNCATEGORIZED}
        return tuple(sorted(found))

    def visible(
        self,
        mode: str,
        *,
        query: str = "",
        category: str = ALL_CATEGORIES,
        favorites_only: bool = False,
        uncategorized_label: str | None = None,
        favorite_mark: str | None = None,
    ) -> tuple[Resource, ...]:
        """Filter and order the collection the way the list does.

        Mirrors ``refresh_view`` (``resource_hub.pyw:2520-2555``): category filter,
        favourites-only filter, substring search over name/kind/target/category/
        note, then a **stable** favourites-first sort.

        ``uncategorized_label`` / ``favorite_mark`` let the caller inject the
        current language's display strings so searching for "未分类" still works;
        the backend itself has no i18n.
        """
        self._require_loaded()
        needle = query.strip().lower()
        result: list[Resource] = []
        for item in self._items[mode]:
            if category != ALL_CATEGORIES and item.category != category:
                continue
            if favorites_only and not item.favorite:
                continue
            if needle:
                parts = [
                    favorite_mark if (favorite_mark and item.favorite) else "",
                    item.name,
                    getattr(item, "kind", ""),
                    item.target,
                    item.category,
                    item.note,
                    uncategorized_label if (uncategorized_label and item.category == UNCATEGORIZED) else "",
                ]
                if needle not in " ".join(parts).lower():
                    continue
            result.append(item)
        # sorted() is stable, so insertion order survives inside each group.
        return tuple(
            sorted(result, key=lambda entry: 0 if entry.favorite else 1)
        )

    def check_paths(self, mode: str) -> PathCheckResult:
        """Report entries whose target no longer exists.

        Links are not checked — the legacy app returns
        ``path_check_links_disabled`` in that case.
        """
        self._require_loaded()
        if mode == "links":
            return PathCheckResult(supported=False)
        missing = tuple(
            item.id for item in self._items["folders"] if not Path(item.target).exists()
        )
        return PathCheckResult(
            supported=True, total=len(self._items["folders"]), missing=missing
        )

    # -- mutations ---------------------------------------------------------
    def add(
        self,
        mode: str,
        *,
        name: str,
        target: str,
        category: str | None = None,
        note: str = "",
    ) -> Resource:
        """Validate, de-duplicate and insert at the top of the collection."""
        self._require_loaded()
        clean_name = name.strip()
        raw_target = target.strip()
        clean_note = note.strip()
        clean_category = normalize_category(category)

        normalized_target, kind = self._validate(mode, clean_name, raw_target)
        if self._find_duplicate(mode, normalized_target) is not None:
            raise DuplicateError(self._duplicate_key(mode))

        item = self._build(
            mode,
            name=clean_name,
            target=normalized_target,
            kind=kind,
            category=clean_category,
            note=clean_note,
        )
        self._items[mode].insert(0, item)
        self._save(mode)
        return item

    def update(
        self,
        mode: str,
        item_id: str,
        *,
        name: str,
        target: str,
        category: str | None = None,
        note: str = "",
    ) -> Resource:
        """Replace an entry in place, preserving ``id``, ``createdAt`` and ``favorite``."""
        self._require_loaded()
        existing = self.get(mode, item_id)
        clean_name = name.strip()
        raw_target = target.strip()

        normalized_target, kind = self._validate(mode, clean_name, raw_target)
        if self._find_duplicate(mode, normalized_target, exclude_id=item_id) is not None:
            raise DuplicateError(self._duplicate_key(mode))

        updated = self._build(
            mode,
            name=clean_name,
            target=normalized_target,
            kind=kind,
            category=normalize_category(category),
            note=note.strip(),
            item_id=item_id,
            created_at=existing.created_at,
            favorite=existing.favorite,
        )
        index = self._items[mode].index(existing)
        self._items[mode][index] = updated
        self._save(mode)
        return updated

    def delete(self, mode: str, item_id: str) -> bool:
        """Remove an entry. Returns ``False`` when the id was already gone."""
        self._require_loaded()
        remaining = [item for item in self._items[mode] if item.id != item_id]
        if len(remaining) == len(self._items[mode]):
            return False
        self._items[mode] = remaining
        self._save(mode)
        return True

    def toggle_favorite(self, mode: str, item_id: str) -> Resource:
        self._require_loaded()
        return self.set_favorite(mode, item_id, not self.get(mode, item_id).favorite)

    def set_favorite(self, mode: str, item_id: str, value: bool) -> Resource:
        self._require_loaded()
        item = self.get(mode, item_id)
        if item.favorite == value:
            return item
        updated = with_changes(item, favorite=value)
        self._items[mode][self._items[mode].index(item)] = updated
        self._save(mode)
        return updated

    def add_dropped(self, paths: Sequence[str]) -> DropResult:
        """Add dropped files/folders.

        Invalid (non-existent) paths are counted, not raised; duplicates are
        skipped. New entries go to the top in reverse input order — that is the
        legacy behaviour (``resource_hub.pyw:2301`` inserts at 0 in a loop) and is
        preserved so Phase 5 can compare side by side.
        """
        self._require_loaded()
        valid: list[Path] = []
        invalid = 0
        for raw in paths:
            normalized = normalize_folder_path(str(raw))
            if not normalized:
                invalid += 1
                continue
            candidate = Path(normalized)
            if candidate.exists():
                valid.append(candidate)
            else:
                invalid += 1

        existing = {
            comparable_value(item.target, "folders") for item in self._items["folders"]
        }
        added = 0
        skipped = 0
        for candidate in valid:
            key = comparable_value(str(candidate), "folders")
            if key in existing:
                skipped += 1
                continue
            self._items["folders"].insert(
                0,
                Folder(
                    id=str(uuid.uuid4()),
                    name=candidate.name or str(candidate),
                    path=str(candidate),
                    kind="folder" if candidate.is_dir() else "file",
                    category=UNCATEGORIZED,
                    created_at=now_iso(),
                ),
            )
            existing.add(key)
            added += 1
        if added:
            self._save("folders")
        return DropResult(added=added, skipped=skipped, invalid=invalid)

    # -- backup ------------------------------------------------------------
    def export_payload(self, mode: str) -> list[dict[str, Any]]:
        """Serialise the collection for a backup file."""
        self._require_loaded()
        return [item.to_json() for item in self._items[mode]]

    def import_payload(self, mode: str, payload: Any) -> ImportResult:
        """Replace the collection with a backup file's contents.

        Legacy semantics (``resource_hub.pyw:2841``): the import **replaces** the
        current collection rather than merging, and de-duplicates within the
        payload only.
        """
        self._require_loaded()
        if not isinstance(payload, list):
            raise ServiceError("import_failed", "backup must be a JSON array")

        try:
            normalized = [
                parse_entry(mode, raw)
                for raw in payload
                if isinstance(raw, Mapping) and is_complete(mode, raw)
            ]
        except (TypeError, ValueError) as exc:
            raise ServiceError("import_failed", str(exc)) from exc

        deduped: list[Resource] = []
        seen: set[str] = set()
        skipped = 0
        for item in normalized:
            key = comparable_value(item.target, mode)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            deduped.append(item)

        self._items[mode] = deduped
        self._save(mode)
        return ImportResult(imported=len(deduped), skipped=skipped)

    # -- internals ---------------------------------------------------------
    def _validate(self, mode: str, name: str, raw_target: str) -> tuple[str, str]:
        """Apply the same checks, in the same order, as ``save_current``."""
        if mode == "links":
            if not name:
                raise ValidationError("enter_link_name")
            if not raw_target:
                raise ValidationError("enter_link_path")
            normalized = normalize_url(raw_target)
            if not normalized.startswith(("http://", "https://")):
                raise ValidationError("invalid_link_path")
            return normalized, "link"

        if not name:
            raise ValidationError("enter_folder_name")
        if not raw_target:
            raise ValidationError("enter_folder_path")
        normalized = normalize_folder_path(raw_target)
        path = Path(normalized)
        if not path.exists():
            raise ValidationError("invalid_folder_path")
        return normalized, ("folder" if path.is_dir() else "file")

    def _find_duplicate(
        self, mode: str, normalized_target: str, *, exclude_id: str | None = None
    ) -> Resource | None:
        key = comparable_value(normalized_target, mode)
        for item in self._items[mode]:
            if exclude_id is not None and item.id == exclude_id:
                continue
            if comparable_value(item.target, mode) == key:
                return item
        return None

    @staticmethod
    def _duplicate_key(mode: str) -> str:
        return "duplicate_link_path" if mode == "links" else "duplicate_folder_path"

    def _build(
        self,
        mode: str,
        *,
        name: str,
        target: str,
        kind: str,
        category: str,
        note: str,
        item_id: str | None = None,
        created_at: str | None = None,
        favorite: bool = False,
    ) -> Resource:
        common = {
            "id": item_id or str(uuid.uuid4()),
            "name": name,
            "category": category,
            "note": note,
            "favorite": favorite,
            "created_at": created_at or now_iso(),
        }
        if mode == "links":
            return Site(url=target, **common)
        return Folder(path=target, kind=kind, **common)

    def replace_all(self, mode: str, items: Iterable[Resource]) -> None:
        """Swap a collection wholesale (used by tests and future undo support)."""
        self._require_loaded()
        self._items[mode] = list(items)
        self._save(mode)

    def rename_category(self, mode: str, old: str, new: str) -> int:
        """Rename a category across a collection. Returns the number of changes."""
        self._require_loaded()
        target = normalize_category(new)
        changed = 0
        updated: list[Resource] = []
        for item in self._items[mode]:
            if item.category == old:
                updated.append(replace(item, category=target))
                changed += 1
            else:
                updated.append(item)
        if changed:
            self._items[mode] = updated
            self._save(mode)
        return changed
