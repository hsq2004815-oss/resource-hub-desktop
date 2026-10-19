"""Read-only bridge to the local Chrome / Edge bookmark stores.

The backend imports the user's browser bookmarks into ``sites.json`` without a
browser extension and without network access: it discovers the browser profile
directories, parses the bookmark JSON file Chrome and Edge share — ``Bookmarks``
for signed-out profiles and ``AccountBookmarks`` for Chrome profiles signed in
with bookmark sync — and appends the new links once.

Browser files are **only ever read** — never modified. Chrome and Edge rewrite
their bookmark file in place on every change, so a read that lands mid-write can
see invalid JSON; such a read is retried once before the file is treated as
unreadable instead of raising.

Discovery roots
---------------
By default the two Windows browser data directories below ``%LOCALAPPDATA%``
are used (Chrome then Edge). The environment variable
``RH_BROWSER_DATA_DIRS`` replaces them with a ``os.pathsep``-separated list of
browser *User Data* directories; an **empty** value disables discovery. This is
used by the tests (so they never depend on the developer's real browser) and by
portable installs. A root's browser label is inferred from its path, with the
directory name as the fallback.

Sync state
----------
``.resourcehub-meta.json`` (already used for the order migration) gains a
``bookmarks`` object with ``seenUrls`` / ``lastSyncAt``. Every collected URL is
remembered, so a resource the user deletes from the tool is never resurrected by
a later sync. All other keys in that file — especially ``orderVersion`` — are
preserved on write.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .normalize import now_iso
from .service import ORDER_META_FILENAME, ORDER_VERSION, ResourceService
from .settings import Settings
from .storage import CorruptDataError, JsonFileStore

#: Replaces the default browser roots with ``os.pathsep``-separated "User Data"
#: directories. An empty value means "discover nothing".
BROWSER_DATA_DIRS_ENV = "RH_BROWSER_DATA_DIRS"

CHROME_DATA_SUBPATH = ("Google", "Chrome", "User Data")
EDGE_DATA_SUBPATH = ("Microsoft", "Edge", "User Data")

#: Categories the user chose for the two top-level bookmark containers.
BOOKMARK_BAR_CATEGORY = "书签栏"
OTHER_BOOKMARKS_CATEGORY = "其他收藏"
CUSTOM_PROFILE_LABEL = "自定义"

#: Chrome/Edge bookmark roots, mapped to the category of their direct children.
ROOT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("bookmark_bar", BOOKMARK_BAR_CATEGORY),
    ("other", OTHER_BOOKMARKS_CATEGORY),
    ("synced", OTHER_BOOKMARKS_CATEGORY),
)

#: Watcher timings (seconds).
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_REDISCOVER_INTERVAL = 30.0
CHANGE_DEBOUNCE_SECONDS = 0.6
READ_RETRY_DELAY_SECONDS = 0.06

#: Bookmark files a profile directory may contain, most authoritative first.
#: Chrome writes ``AccountBookmarks`` for profiles signed in with bookmark sync
#: (it may not write ``Bookmarks`` at all); Edge and signed-out profiles use
#: ``Bookmarks``.
_PROFILE_BOOKMARK_FILENAMES = ("AccountBookmarks", "Bookmarks")
_META_BOOKMARKS_KEY = "bookmarks"
_META_SEEN_KEY = "seenUrls"
_META_LAST_SYNC_KEY = "lastSyncAt"
_PROFILE_PREFIX = "profile "
_PROFILE_SORT_LAST = 1 << 30


# --- data objects ----------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BookmarkProfile:
    """One browser profile and the bookmark files that own it.

    A signed-in Chrome profile can keep bookmarks in ``AccountBookmarks`` *and*
    ``Bookmarks`` at the same time (the UI merges both), so a profile collects
    every readable file and the import de-duplicates the URLs across them.
    """

    label: str
    paths: tuple[Path, ...]

    @property
    def path(self) -> Path:
        """The primary bookmark file (first one discovered)."""
        return self.paths[0]


@dataclass(frozen=True, slots=True)
class BookmarkEntry:
    """One accepted bookmark plus the category the import will assign."""

    name: str
    url: str
    category: str


@dataclass(frozen=True, slots=True)
class CollectedProfile:
    """Profile statistics included in the protocol results."""

    label: str
    path: Path
    bookmarks: int

    def to_json(self) -> dict[str, Any]:
        return {"label": self.label, "path": str(self.path), "bookmarks": self.bookmarks}


@dataclass(frozen=True, slots=True)
class BookmarkCollection:
    """Everything one discovery + parse pass produced.

    ``entries`` items are ``(profile label, name, normalized URL, category)`` in
    file order; ``total`` is ``len(entries)`` and ``profiles`` carries the
    per-profile counts shown in the UI.
    """

    entries: tuple[tuple[str, str, str, str], ...]
    profiles: tuple[CollectedProfile, ...]
    total: int

    def profile_json(self) -> list[dict[str, Any]]:
        return [profile.to_json() for profile in self.profiles]


# --- URL handling ----------------------------------------------------------
def dedup_key(url: str) -> str:
    """De-duplication key: trimmed, lowercased, trailing slashes removed."""
    return url.strip().lower().rstrip("/")


def normalize_bookmark_url(raw: str) -> str | None:
    """Return ``raw`` with a lowercased http(s) scheme, or ``None`` to skip it.

    Only ``http`` / ``https`` links become resources. ``chrome://``,
    ``edge://``, ``about:``, ``javascript:``, ``data:``, ``file://`` and every
    other scheme is browser-specific or unsafe to open through the tool.
    """
    value = str(raw).strip()
    if not value:
        return None
    scheme, separator, rest = value.partition("://")
    if not separator:
        return None
    scheme = scheme.lower()
    if scheme not in ("http", "https"):
        return None
    return f"{scheme}://{rest}"


def _url_host(url: str) -> str:
    """Best-effort host extraction, used when a bookmark has no name."""
    _, _, rest = url.partition("://")
    return rest.split("/", 1)[0].strip()


def _entry_name(node: Mapping[str, Any], url: str) -> str:
    name = str(node.get("name") or "").strip()
    if name:
        return name
    return _url_host(url) or url


# --- reading / parsing -----------------------------------------------------
def _read_payload(path: Path) -> Any | None:
    """Parse one ``Bookmarks`` file, tolerating a read that lands mid-write.

    One retry after a short delay is enough in practice; after that the file is
    treated as unreadable rather than raising into the caller.
    """
    for attempt in (0, 1):
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
            return json.loads(text)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            if attempt == 0:
                time.sleep(READ_RETRY_DELAY_SECONDS)
    return None


def _walk_nodes(
    children: Any,
    folder_names: tuple[str, ...],
    root_category: str,
) -> list[BookmarkEntry]:
    """Depth-first walk in file order, building categories from folder names."""
    entries: list[BookmarkEntry] = []
    if not isinstance(children, list):
        return entries
    for node in children:
        if not isinstance(node, Mapping):
            continue
        node_type = node.get("type")
        if node_type == "url":
            url = normalize_bookmark_url(str(node.get("url") or ""))
            if url is None:
                continue
            category = "/".join(folder_names) if folder_names else root_category
            entries.append(BookmarkEntry(_entry_name(node, url), url, category))
        elif node_type == "folder":
            folder_name = str(node.get("name") or "").strip()
            nested = folder_names + ((folder_name,) if folder_name else ())
            entries.extend(_walk_nodes(node.get("children"), nested, root_category))
    return entries


def parse_bookmarks(path: Path) -> list[BookmarkEntry] | None:
    """Parse one ``Bookmarks`` file.

    ``None`` means the file is unreadable or does not look like a bookmark
    file; callers omit such profiles instead of surfacing an error.
    """
    payload = _read_payload(path)
    if not isinstance(payload, Mapping):
        return None
    roots = payload.get("roots")
    if not isinstance(roots, Mapping):
        return None
    entries: list[BookmarkEntry] = []
    for root_key, category in ROOT_CATEGORIES:
        root = roots.get(root_key)
        if not isinstance(root, Mapping):
            continue
        entries.extend(_walk_nodes(root.get("children"), (), category))
    return entries


# --- profile discovery -----------------------------------------------------
def _readable_bookmark_files(profile_dir: Path) -> list[Path]:
    """Every readable bookmark JSON file in ``profile_dir``, primary first.

    ``AccountBookmarks`` comes first: a Chrome profile signed in with bookmark
    sync keeps its bookmarks there and may not write ``Bookmarks`` at all. Both
    files are returned when present, because Chrome merges them in its own UI.
    """
    files: list[Path] = []
    for name in _PROFILE_BOOKMARK_FILENAMES:
        candidate = profile_dir / name
        try:
            if candidate.is_file() and os.access(candidate, os.R_OK):
                files.append(candidate)
        except OSError:
            continue
    return files


def _profile_sort_key(directory: Path) -> tuple[int, int, str]:
    """``Default`` first, then ``Profile N`` numerically (Profile 2 < 10)."""
    name = directory.name
    if name.casefold() == "default":
        return (0, 0, "")
    suffix = name[len(_PROFILE_PREFIX):].strip()
    try:
        number = int(suffix)
    except ValueError:
        number = _PROFILE_SORT_LAST
    return (1, number, name.casefold())


def _scan_user_data(root: Path, label_prefix: str) -> list[BookmarkProfile]:
    """Readable profiles of one ``User Data`` directory, in import order."""
    try:
        if not root.is_dir():
            return []
        directories = [
            child
            for child in root.iterdir()
            if child.is_dir()
            and (
                child.name.casefold() == "default"
                or child.name.casefold().startswith(_PROFILE_PREFIX)
            )
        ]
    except OSError:
        return []
    profiles: list[BookmarkProfile] = []
    for directory in sorted(directories, key=_profile_sort_key):
        bookmarks = _readable_bookmark_files(directory)
        if not bookmarks:
            continue
        profiles.append(
            BookmarkProfile(f"{label_prefix} · {directory.name}", tuple(bookmarks))
        )
    return profiles


def _browser_label(root: Path) -> str:
    """Infer the browser name for a discovery root (used in profile labels)."""
    name = root.name
    if name.casefold() in ("user data", "userdata") and root.parent.name:
        name = root.parent.name
    lowered = name.casefold()
    if lowered == "chrome":
        return "Chrome"
    if lowered == "edge":
        return "Edge"
    return name or "浏览器"


def browser_roots() -> list[tuple[str, Path]]:
    """Discovery roots as ``(browser label, User Data dir)`` in priority order.

    ``RH_BROWSER_DATA_DIRS`` replaces the defaults entirely; an empty value
    yields no roots at all (used by tests and by "bridge off" setups). Missing
    default roots are skipped silently.
    """
    override = os.environ.get(BROWSER_DATA_DIRS_ENV)
    if override is not None:
        roots = [part.strip() for part in override.split(os.pathsep) if part.strip()]
        return [(_browser_label(Path(root)), Path(root)) for root in roots]

    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return []
    base = Path(local_app_data)
    roots: list[tuple[str, Path]] = []
    for subpath in (CHROME_DATA_SUBPATH, EDGE_DATA_SUBPATH):
        root = base.joinpath(*subpath)
        try:
            exists = root.is_dir()
        except OSError:
            exists = False
        if exists:
            roots.append((_browser_label(root), root))
    return roots


def _custom_profiles(settings: Settings) -> list[BookmarkProfile]:
    """Profiles from ``Settings.bookmark_custom_dir``; invalid paths are ignored.

    Accepted shapes: a ``Bookmarks`` / ``AccountBookmarks`` file, a profile
    directory containing one, or a ``User Data`` directory whose profiles are
    scanned.
    """
    raw = str(settings.bookmark_custom_dir or "").strip()
    if not raw:
        return []
    path = Path(os.path.expandvars(raw)).expanduser()
    try:
        if path.is_file():
            known = {name.casefold() for name in _PROFILE_BOOKMARK_FILENAMES}
            if path.name.casefold() in known:
                return [BookmarkProfile(CUSTOM_PROFILE_LABEL, (path,))]
            return []
        if not path.is_dir():
            return []
        direct = _readable_bookmark_files(path)
        if direct:
            return [BookmarkProfile(CUSTOM_PROFILE_LABEL, tuple(direct))]
        return _scan_user_data(path, CUSTOM_PROFILE_LABEL)
    except OSError:
        return []


def _add_profile(
    profiles: list[BookmarkProfile], seen: set[str], profile: BookmarkProfile
) -> None:
    key = os.pathsep.join(
        os.path.normcase(os.path.abspath(str(path))) for path in profile.paths
    )
    if key in seen:
        return
    seen.add(key)
    profiles.append(profile)


def discover_profiles(settings: Settings) -> list[BookmarkProfile]:
    """All readable profile bookmark files, in display/import order.

    Browser profiles come first (Chrome then Edge, ``Default`` before
    ``Profile N``), the custom directory last. A path is only returned once, so
    pointing the custom dir at a default location cannot import twice.
    """
    profiles: list[BookmarkProfile] = []
    seen: set[str] = set()
    for label, root in browser_roots():
        for profile in _scan_user_data(root, label):
            _add_profile(profiles, seen, profile)
    for profile in _custom_profiles(settings):
        _add_profile(profiles, seen, profile)
    return profiles


def collect_bookmarks(settings: Settings) -> BookmarkCollection:
    """Discover profiles and parse every bookmark file (read-only)."""
    entries: list[tuple[str, str, str, str]] = []
    profiles: list[CollectedProfile] = []
    for profile in discover_profiles(settings):
        parsed_entries: list[BookmarkEntry] = []
        read_any = False
        for path in profile.paths:
            parsed = parse_bookmarks(path)
            if parsed is None:
                continue
            read_any = True
            parsed_entries.extend(parsed)
        if not read_any:
            continue
        for entry in parsed_entries:
            entries.append((profile.label, entry.name, entry.url, entry.category))
        profiles.append(
            CollectedProfile(profile.label, profile.path, len(parsed_entries))
        )
    return BookmarkCollection(tuple(entries), tuple(profiles), len(entries))


# --- sync engine -----------------------------------------------------------
class BookmarkSyncEngine:
    """Imports new bookmarks into ``sites.json`` and remembers what was seen."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self._meta_store = JsonFileStore(self.base_dir / ORDER_META_FILENAME)

    # -- metadata ----------------------------------------------------------
    def _load_meta(self) -> dict[str, Any]:
        """The meta payload, starting from an empty mapping when unusable."""
        try:
            payload = self._meta_store.load_or_none()
        except CorruptDataError:
            # The order migration treats a corrupt marker as "do not migrate".
            # Writing that decision back keeps the next load from re-pinning
            # favourites and destroying a manually arranged order.
            return {"orderVersion": ORDER_VERSION}
        return dict(payload) if isinstance(payload, Mapping) else {}

    @staticmethod
    def _parse_state(meta: Mapping[str, Any]) -> tuple[set[str], str | None]:
        """The ``bookmarks`` object of the meta payload, defaulting to empty."""
        raw = meta.get(_META_BOOKMARKS_KEY)
        if not isinstance(raw, Mapping):
            return set(), None
        seen_raw = raw.get(_META_SEEN_KEY)
        seen = (
            {str(value) for value in seen_raw if isinstance(value, str)}
            if isinstance(seen_raw, list)
            else set()
        )
        last_raw = raw.get(_META_LAST_SYNC_KEY)
        last_sync = last_raw if isinstance(last_raw, str) and last_raw else None
        return seen, last_sync

    def _load_state(self) -> tuple[set[str], str | None]:
        return self._parse_state(self._load_meta())

    # -- reverse sync (Phase 18) -------------------------------------------
    def seen_urls(self) -> set[str]:
        """Snapshot of the normalized URLs a previous sync has already imported."""
        return self._load_state()[0]

    def forget_seen(self, urls: Iterable[str]) -> int:
        """Drop seen URLs from the ledger so re-bookmarking one imports it again.

        The browser extension calls this when the user deletes a bookmark in the
        browser: the bookmark is gone, so the "never resurrect a deleted
        resource" ledger must forget it (otherwise re-adding the same bookmark
        later would be ignored forever). Every other key in the meta file —
        especially ``orderVersion`` — and the previous ``lastSyncAt`` are kept.

        Returns how many of ``urls`` were actually in the ledger.
        """
        targets = {dedup_key(str(url)) for url in urls}
        if not targets:
            return 0
        meta = self._load_meta()
        seen, last_sync = self._parse_state(meta)
        forgotten = seen & targets
        if not forgotten:
            return 0
        meta[_META_BOOKMARKS_KEY] = {
            _META_SEEN_KEY: sorted(seen - forgotten),
            _META_LAST_SYNC_KEY: last_sync,
        }
        self._meta_store.save(meta)
        return len(forgotten)

    # -- read-only views ---------------------------------------------------
    def collect(self, settings: Settings) -> BookmarkCollection:
        """Discover and parse every bookmark file (no state is changed)."""
        return collect_bookmarks(settings)

    def status(self, settings: Settings) -> dict[str, Any]:
        """Read-only snapshot for ``bookmarks.status``."""
        collection = collect_bookmarks(settings)
        seen, last_sync = self._load_state()
        return {
            "enabled": bool(settings.bookmark_sync_enabled),
            "customDir": settings.bookmark_custom_dir,
            "profiles": collection.profile_json(),
            "lastSyncAt": last_sync,
            "syncedUrls": len(seen),
        }

    # -- import ------------------------------------------------------------
    def sync(self, service: ResourceService, settings: Settings) -> dict[str, Any]:
        """Append newly found bookmarks to the links collection.

        A URL is imported once: it is skipped when the collection already holds
        it, when a previous sync saw it (even if the user deleted the resource
        since), or when another profile in the same batch already provided it.
        """
        collection = collect_bookmarks(settings)
        if not collection.profiles:
            # No browser profile found: do not stamp a "last sync" time and do
            # not touch the seen ledger — the first real sync should still import
            # everything the user already bookmarked.
            _seen, last_sync = self._load_state()
            return {
                "added": 0,
                "skipped": 0,
                "total": 0,
                "profiles": [],
                "lastSyncAt": last_sync,
            }
        meta = self._load_meta()
        seen, _last_sync = self._parse_state(meta)
        existing = {dedup_key(item.target) for item in service.items("links")}

        batch: list[tuple[str, str, str | None]] = []
        batch_keys: set[str] = set()
        for _label, name, url, category in collection.entries:
            key = dedup_key(url)
            if key in existing or key in seen or key in batch_keys:
                continue
            batch_keys.add(key)
            batch.append((name, url, category))

        created = service.add_synced("links", batch) if batch else []

        last_sync = now_iso()
        seen.update(dedup_key(entry[2]) for entry in collection.entries)
        bookmark_state = {
            _META_SEEN_KEY: sorted(seen),
            _META_LAST_SYNC_KEY: last_sync,
        }
        if meta.get(_META_BOOKMARKS_KEY) != bookmark_state:
            meta[_META_BOOKMARKS_KEY] = bookmark_state
            self._meta_store.save(meta)

        return {
            "added": len(created),
            "skipped": collection.total - len(created),
            "total": collection.total,
            "profiles": collection.profile_json(),
            "lastSyncAt": last_sync,
        }


# --- watcher ---------------------------------------------------------------
class BookmarkWatcher:
    """Polls the discovered bookmark files on a daemon thread.

    Only an mtime/size change triggers a sync, and a short debounce comes first
    because a browser rewrite lands as a burst of writes. The service write is
    done under the caller's lock so it can never interleave with a protocol
    handler. Every exception is swallowed: a browser profile we cannot read must
    never take the backend down or stop the thread.
    """

    def __init__(
        self,
        engine: BookmarkSyncEngine,
        service: ResourceService,
        state_getter: Callable[[], Settings],
        on_sync: Callable[[dict[str, Any]], None],
        interval: float = DEFAULT_POLL_INTERVAL,
        rediscover_interval: float = DEFAULT_REDISCOVER_INTERVAL,
        lock: threading.RLock | None = None,
    ) -> None:
        self._engine = engine
        self._service = service
        self._state_getter = state_getter
        self._on_sync = on_sync
        self._interval = max(0.01, float(interval))
        self._rediscover_interval = max(self._interval, float(rediscover_interval))
        self._lock = lock
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._watched: dict[str, tuple[int, int]] | None = None
        self._last_discovery = 0.0

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        """Start the daemon thread (idempotent)."""
        if self.running:
            return
        self._stop_event.clear()
        self._watched = None
        self._last_discovery = 0.0
        self._thread = threading.Thread(
            target=self._run, name="bookmark-watcher", daemon=True
        )
        self._thread.start()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the thread and wait briefly for it to finish (idempotent)."""
        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout)

    # -- polling -----------------------------------------------------------
    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self._poll()
            except Exception:  # noqa: BLE001 - a broken watcher must never die
                # Browser files and settings are outside our control; one bad
                # poll must not stop the thread. Not logged to keep stderr quiet
                # on a machine with a half-written profile.
                continue

    def _poll(self) -> None:
        settings = self._state_getter()
        if not settings.bookmark_sync_enabled:
            # Forget the baseline so re-enabling starts from a fresh snapshot:
            # bookmarks added while the bridge was off are not silently imported.
            self._watched = None
            return

        now = time.monotonic()
        if self._watched is None:
            self._watched = self._snapshot(settings)
            self._last_discovery = now
            # First poll after start (or after re-enabling) also syncs: this is
            # the "import what already exists" pass, and it catches bookmarks
            # added while the app was closed / the bridge was switched off.
            self._sync(settings)
            return

        if now - self._last_discovery >= self._rediscover_interval:
            fresh = self._snapshot(settings)
            appeared = [path for path in fresh if path not in self._watched]
            # Keep the previous stamp for paths already watched, so a change
            # that landed just before this discovery is still detected.
            self._watched = {
                path: self._watched.get(path, stamp) for path, stamp in fresh.items()
            }
            self._last_discovery = now
            if not appeared:
                return
        elif not any(
            self._stat(path) != stamp for path, stamp in self._watched.items()
        ):
            return

        self._sync(settings)

    def _sync(self, settings: Settings) -> None:
        if self._stop_event.wait(CHANGE_DEBOUNCE_SECONDS):
            return
        if self._lock is not None:
            with self._lock:
                result = self._engine.sync(self._service, settings)
                if result["added"] > 0:
                    self._on_sync(result)
        else:
            result = self._engine.sync(self._service, settings)
            if result["added"] > 0:
                self._on_sync(result)
        self._watched = self._snapshot(settings)
        self._last_discovery = time.monotonic()

    def _snapshot(self, settings: Settings) -> dict[str, tuple[int, int]]:
        snapshot: dict[str, tuple[int, int]] = {}
        for profile in discover_profiles(settings):
            for path in profile.paths:
                stamp = self._stat(str(path))
                if stamp is not None:
                    snapshot[str(path)] = stamp
        return snapshot

    @staticmethod
    def _stat(path: str) -> tuple[int, int] | None:
        try:
            stat = os.stat(path)
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)
