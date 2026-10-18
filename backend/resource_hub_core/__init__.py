"""Headless business layer for Resource Hub.

The package has **no UI dependency** (no Tk, no pystray) so it can run inside a
windowless backend process. Public surface:

    from resource_hub_core import ResourceService, SettingsStore

    service = ResourceService(Path(app_dir))
    service.load()                       # may raise CorruptDataError
    service.add("links", name="GitHub", target="github.com")

See ``migration/phase3-business-layer.md`` for the porting rules.
"""

from .models import (
    ALL_CATEGORIES,
    UNCATEGORIZED,
    Folder,
    Resource,
    Site,
    parse_entry,
)
from .normalize import (
    comparable_value,
    format_added,
    normalize_folder_path,
    normalize_url,
    parse_hotkey_id,
)
from .service import (
    DropResult,
    DuplicateError,
    ImportResult,
    NotFoundError,
    PathCheckResult,
    ResourceService,
    ServiceError,
    ValidationError,
)
from .settings import Settings, SettingsStore
from .storage import CorruptDataError, JsonFileStore, StorageError

__all__ = [
    "ALL_CATEGORIES",
    "UNCATEGORIZED",
    "CorruptDataError",
    "DropResult",
    "DuplicateError",
    "Folder",
    "ImportResult",
    "JsonFileStore",
    "NotFoundError",
    "PathCheckResult",
    "Resource",
    "ResourceService",
    "ServiceError",
    "Settings",
    "SettingsStore",
    "Site",
    "StorageError",
    "ValidationError",
    "comparable_value",
    "format_added",
    "normalize_folder_path",
    "normalize_url",
    "parse_entry",
    "parse_hotkey_id",
]

__version__ = "0.3.0"
