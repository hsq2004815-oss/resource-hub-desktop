"""stdio JSON Lines protocol between the Flutter client and the Python backend.

One JSON object per line, UTF-8, ``\\n`` terminated. Three frame kinds:

Request (client -> backend)::

    {"id": 1, "method": "resources.list", "params": {"mode": "folders"}}

Success response::

    {"id": 1, "ok": true, "result": {"items": [...], "total": 11}}

Failure response::

    {"id": 1, "ok": false, "error": {"code": "validation",
                                     "key": "enter_link_name", "detail": "..."}}

Event (backend -> client, unsolicited)::

    {"event": "hotkey", "payload": {"action": "toggle"}}

Events carry no ``id``; the client routes them by ``event``. They exist because a
global hotkey press is not a reply to anything — the request/response-only design
in the Phase 1 audit could not express it (see ADR-001 §5).

Design notes
------------
* stdout carries **only** protocol frames. Diagnostics go to stderr.
* Every write takes a lock and ends with a flush, because events are emitted from
  the hotkey thread while the main thread may be writing a response.
* ``CorruptDataError`` at startup is not fatal: the server reports
  ``dataStatus: "corrupt"`` and refuses mutations, so the UI can tell the user
  instead of silently losing data (ADR-001 D3).
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, IO, Mapping

from .ai import AI_KEY_FILENAME, AiClient, AiError, AiItem, AiKeyStore, AiKeyStoreError
from .bookmark_bridge import BookmarkBridge
from .bookmarks import BookmarkSyncEngine, BookmarkWatcher, dedup_key
from .favicons import FaviconStore
from .browsers import find_browser, installed_browsers
from .fs import list_children, open_fs_path, reveal_fs_path
from .hotkey import GlobalHotkeyListener, is_combination_available
from .launcher import open_link, open_path, reveal_path
from .mousehook import MouseSideButtonListener
from .models import ALL_CATEGORIES, UNCATEGORIZED, Resource
from .service import (
    DuplicateError,
    NotFoundError,
    ResourceService,
    ServiceError,
    ValidationError,
)
from .settings import Settings, SettingsStore
from .storage import CorruptDataError

PROTOCOL_VERSION = 1

#: ``ai.suggestCategories`` defaults / clamps (Phase 22). The cap keeps one
#: synchronous request (and its token cost) bounded.
AI_SUGGESTION_LIMIT_DEFAULT = 40
AI_SUGGESTION_LIMIT_MAX = 60

#: Error codes the client can branch on. ``key`` (when present) is an i18n key
#: from the legacy string table; ``detail`` is for logs, not for users.
ERROR_CODES = (
    "bad_request",
    "validation",
    "duplicate",
    "not_found",
    "corrupt_data",
    "unknown_method",
    "operation_failed",
    "internal",
    "ai_disabled",
    "ai_not_configured",
    "ai_request_failed",
)


class ProtocolError(Exception):
    """A request that cannot be served; becomes an error response."""

    def __init__(self, code: str, detail: str = "", key: str | None = None) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail
        self.key = key

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "detail": self.detail}
        if self.key:
            payload["key"] = self.key
        return payload


def bookmark_event_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    """The ``bookmarks`` event payload a client needs to refresh its view."""
    return {
        "added": result["added"],
        "lastSyncAt": result["lastSyncAt"],
        "profiles": list(result["profiles"]),
    }


class FrameWriter:
    """Serialises frame writes across threads."""

    def __init__(self, stream: IO[str]) -> None:
        self._stream = stream
        self._lock = threading.Lock()

    def write(self, frame: Mapping[str, Any]) -> None:
        line = json.dumps(frame, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()

    def event(self, name: str, payload: Mapping[str, Any] | None = None) -> None:
        self.write({"event": name, "payload": dict(payload or {})})

    def response(self, request_id: Any, result: Mapping[str, Any]) -> None:
        self.write({"id": request_id, "ok": True, "result": dict(result)})

    def error(self, request_id: Any, error: ProtocolError) -> None:
        self.write({"id": request_id, "ok": False, "error": error.to_json()})


@dataclass
class ServerState:
    """Mutable state shared by handlers."""

    base_dir: Path
    service: ResourceService
    settings_store: SettingsStore
    settings: Settings
    bookmark_engine: BookmarkSyncEngine
    #: Phase 22: DPAPI-encrypted API key for the optional AI suggestions. Kept
    #: out of ``settings.json`` on purpose (that file is plain JSON).
    ai_key_store: AiKeyStore
    #: Cached per-site favicons (``data/favicons``); the UI asks for a refresh
    #: once at startup and after imports, so no network happens by default.
    favicons: FaviconStore
    load_error: str | None = None
    #: Serialises every protocol handler with the bookmark watcher's sync, so a
    #: background import can never interleave with a user-triggered write.
    bookmark_lock: threading.RLock = field(default_factory=threading.RLock)
    bookmark_watcher: BookmarkWatcher | None = None
    #: Loopback HTTP server the browser extension talks to (Phase 18); ``None``
    #: when it is not running (corrupt data, bind failure, after shutdown).
    bookmark_bridge: BookmarkBridge | None = None
    hotkey: list[GlobalHotkeyListener] = field(default_factory=list)
    #: Low-level mouse hook for the opt-in side-button quick panels; ``None``
    #: when the feature is off or the hook could not be installed.
    mouse_hook: MouseSideButtonListener | None = None


class Dispatcher:
    """Maps ``method`` names to service calls. No I/O except through the writer."""

    def __init__(self, state: ServerState, writer: FrameWriter) -> None:
        self.state = state
        self.writer = writer
        self._favicon_lock = threading.Lock()
        self._favicon_pending: list[str] = []
        self._favicon_thread: threading.Thread | None = None
        self._handlers: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
            "app.hello": self._hello,
            "app.shutdown": self._shutdown,
            "bookmarks.status": self._bookmarks_status,
            "bookmarks.sync": self._bookmarks_sync,
            "browsers.list": self._browsers_list,
            "favicons.map": self._favicons_map,
            "favicons.refresh": self._favicons_refresh,
            "bookmarks.extensionStatus": self._bookmarks_extension_status,
            "bookmarks.matches": self._bookmarks_matches,
            "ai.status": self._ai_status,
            "ai.setKey": self._ai_set_key,
            "ai.suggestCategories": self._ai_suggest_categories,
            "resources.list": self._list,
            "resources.add": self._add,
            "resources.update": self._update,
            "resources.delete": self._delete,
            "resources.favorite": self._favorite,
            "resources.reorder": self._reorder,
            "resources.checkPaths": self._check_paths,
            "resources.open": self._open,
            "resources.reveal": self._reveal,
            "resources.drop": self._drop,
            "resources.export": self._export,
            "resources.import": self._import,
            "fs.children": self._fs_children,
            "fs.open": self._fs_open,
            "fs.reveal": self._fs_reveal,
            "settings.get": self._settings_get,
            "settings.set": self._settings_set,
            "settings.probeHotkey": self._probe_hotkey,
            "hotkey.start": self._hotkey_start,
            "hotkey.stop": self._hotkey_stop,
        }

    @property
    def methods(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def dispatch(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        # Held for the whole handler: the bookmark watcher takes the same lock
        # around its background sync, so the two can never interleave writes.
        with self.state.bookmark_lock:
            handler = self._handlers.get(method)
            if handler is None:
                raise ProtocolError("unknown_method", f"no method named {method!r}")
            return handler(params)

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _require_mode(params: Mapping[str, Any]) -> str:
        mode = params.get("mode")
        if mode not in ("links", "folders"):
            raise ProtocolError(
                "bad_request", "params.mode must be 'links' or 'folders'"
            )
        return str(mode)

    @staticmethod
    def _require_str(params: Mapping[str, Any], name: str) -> str:
        value = params.get(name)
        if not isinstance(value, str):
            raise ProtocolError("bad_request", f"params.{name} must be a string")
        return value

    def _require_loaded(self) -> None:
        if self.state.load_error is not None:
            raise ProtocolError(
                "corrupt_data",
                self.state.load_error,
                key="data_corrupt",
            )

    # -- app ---------------------------------------------------------------
    def _hello(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "methods": list(self.methods),
            "dataStatus": "corrupt" if self.state.load_error else "ok",
            "loadError": self.state.load_error,
            "baseDir": str(self.state.base_dir),
        }

    def _shutdown(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self.stop_hotkey()
        self.stop_bookmarks()
        self.stop_bridge()
        return {"shutdown": True}

    # -- bookmarks ---------------------------------------------------------
    def _bookmarks_status(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return self.state.bookmark_engine.status(self.state.settings)

    def _browsers_list(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "browsers": [browser.to_json() for browser in installed_browsers()]
        }

    # -- favicons ----------------------------------------------------------
    def _favicons_map(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return {"icons": self.state.favicons.paths()}

    def _favicons_refresh(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Return the cached map now and fetch the missing hosts in the background."""
        if self.state.load_error is None:
            try:
                urls = [
                    str(item.target)
                    for item in self.state.service.items("links")
                    if getattr(item, "target", "")
                ]
            except Exception:  # noqa: BLE001 - icons must never break the UI
                urls = []
            self._kick_favicons(urls)
        return {"icons": self.state.favicons.paths()}

    def _kick_favicons(self, urls: list[str]) -> None:
        if not urls:
            return
        with self._favicon_lock:
            self._favicon_pending.extend(urls)
            if self._favicon_thread is not None and self._favicon_thread.is_alive():
                return
            self._favicon_thread = threading.Thread(
                target=self._favicon_worker,
                name="favicon-fetch",
                daemon=True,
            )
            self._favicon_thread.start()

    def _favicon_worker(self) -> None:
        store = self.state.favicons
        while True:
            with self._favicon_lock:
                urls = list(dict.fromkeys(self._favicon_pending))
                self._favicon_pending.clear()
                if not urls:
                    self._favicon_thread = None
                    return
            try:
                icons = store.refresh(urls)
                self.writer.event("favicons", {"icons": icons})
            except Exception:  # noqa: BLE001 - a failed icon fetch is harmless
                pass

    def _bookmarks_sync(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        with self.state.bookmark_lock:
            result = self.state.bookmark_engine.sync(
                self.state.service, self.state.settings
            )
        if result["added"] > 0:
            # The response already carries the result; the event keeps every
            # open window consistent, including one that did not send the call.
            self.writer.event("bookmarks", bookmark_event_payload(result))
        return result

    def _bookmarks_extension_status(
        self, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Snapshot for the "browser extension" row in the settings panel."""
        bridge = self.state.bookmark_bridge
        return {
            "connected": bridge is not None and bridge.connected,
            "lastSeenAt": bridge.last_seen_iso if bridge is not None else None,
            "port": bridge.port if bridge is not None else None,
            "pendingCommands": bridge.pending_count() if bridge is not None else 0,
            # The folder the release bundles next to the exe; the UI opens it
            # for "load unpacked" instead of making the user find it.
            "extensionPath": str(self.state.base_dir / "bookmark-extension"),
        }

    def _bookmarks_matches(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Read-only lookup of browser bookmarks by URL (Phase 18).

        Used when the UI already knows a resource URL and wants to offer "also
        remove the browser bookmark". Matching is by ``dedup_key`` so scheme
        case and trailing slashes do not matter; the collection is re-read from
        the browser files, never modified.
        """
        raw_urls = params.get("urls")
        if raw_urls is None:
            return {"matches": []}
        if not isinstance(raw_urls, list) or not all(
            isinstance(url, str) for url in raw_urls
        ):
            raise ProtocolError(
                "bad_request", "params.urls must be an array of strings"
            )
        wanted = {dedup_key(url) for url in raw_urls if url.strip()}
        if not wanted:
            return {"matches": []}
        collection = self.state.bookmark_engine.collect(self.state.settings)
        matches = [
            {
                "url": url,
                "title": name,
                "label": label,
                # Chrome folder path is the import category ("开发/工具").
                "path": category,
            }
            for label, name, url, category in collection.entries
            if dedup_key(url) in wanted
        ]
        return {"matches": matches}

    # -- AI category suggestions (Phase 22) --------------------------------
    def _ai_status(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Snapshot for the AI section of the settings panel."""
        settings = self.state.settings
        return {
            "enabled": settings.ai_enabled,
            "configured": self.state.ai_key_store.has_key(),
            "baseUrl": settings.ai_base_url,
            "model": settings.ai_model,
        }

    def _ai_set_key(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Store or clear the API key. An empty key means "clear it"."""
        raw = params.get("apiKey")
        if not isinstance(raw, str):
            raise ProtocolError("bad_request", "params.apiKey must be a string")
        store = self.state.ai_key_store
        clean = raw.strip()
        try:
            if clean:
                store.save(clean)
            else:
                store.clear()
        except (AiKeyStoreError, OSError, ValueError):
            # Never echo the key or the platform error text: both could end up
            # in the UI status line. The detail below is deliberately generic.
            raise ProtocolError(
                "operation_failed", "could not store the AI API key"
            ) from None
        return {"configured": store.has_key()}

    @staticmethod
    def _suggestion_limit(params: Mapping[str, Any]) -> int:
        """``params.limit``: default 40, clamped to 1..60, tolerant of junk."""
        raw = params.get("limit")
        if isinstance(raw, bool) or not isinstance(raw, int):
            return AI_SUGGESTION_LIMIT_DEFAULT
        return max(1, min(AI_SUGGESTION_LIMIT_MAX, raw))

    def _uncategorized_batch(
        self, limit: int
    ) -> tuple[list[tuple[str, Resource]], list[str]]:
        """Uncategorized items for one request: links first, then folders.

        The per-collection stored order is preserved. ``existing_categories`` is
        the union of the *categorised* categories of both collections, so the
        model can prefer the user's own names.
        """
        service = self.state.service
        existing = {
            category
            for mode in ("links", "folders")
            for category in service.categories(mode)
        }
        batch: list[tuple[str, Resource]] = []
        for mode in ("links", "folders"):
            for item in service.items(mode):
                if item.category != UNCATEGORIZED:
                    continue
                batch.append((mode, item))
                if len(batch) >= limit:
                    return batch, sorted(existing)
        return batch, sorted(existing)

    def _ai_suggest_categories(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Ask the AI endpoint for categories. Suggestion-only: nothing is saved.

        The call is synchronous, so it blocks the (single-threaded) protocol
        loop for up to the client's timeout — documented trade-off in ``ai.py``.
        The default limit is 40 items and the cap is 60; links come first.
        """
        self._require_loaded()
        settings = self.state.settings
        if not settings.ai_enabled:
            raise ProtocolError(
                "ai_disabled", "AI category suggestions are disabled in settings"
            )
        api_key = self.state.ai_key_store.load()
        if not api_key:
            raise ProtocolError(
                "ai_not_configured", "no AI API key is configured"
            )

        batch, existing_categories = self._uncategorized_batch(
            self._suggestion_limit(params)
        )
        if not batch:
            # Nothing to ask about: skip the network round-trip entirely.
            return {
                "model": settings.ai_model,
                "suggestions": [],
                "requestCount": 0,
                "existingCategories": existing_categories,
            }

        items = [
            AiItem(
                mode=mode,
                id=item.id,
                name=item.name,
                target=item.target,
                kind="link"
                if mode == "links"
                else str(getattr(item, "kind", "folder")),
            )
            for mode, item in batch
        ]
        client = AiClient(settings.ai_base_url, settings.ai_model, api_key)
        try:
            reply = client.suggest_categories(items, existing_categories)
        except AiError as exc:
            # ``AiError.detail`` is bounded and never contains the API key.
            raise ProtocolError(
                "ai_request_failed", exc.detail or exc.code
            ) from None

        raw_suggestions = (
            reply.get("suggestions") if isinstance(reply, Mapping) else None
        )
        if not isinstance(raw_suggestions, list):
            raise ProtocolError(
                "ai_request_failed", "the AI endpoint returned an unexpected reply"
            )
        return {
            "model": settings.ai_model,
            "suggestions": self._validate_suggestions(raw_suggestions, batch),
            "requestCount": len(batch),
            "existingCategories": existing_categories,
        }

    def _validate_suggestions(
        self,
        raw_suggestions: list[Any],
        batch: list[tuple[str, Resource]],
    ) -> list[dict[str, Any]]:
        """Keep only suggestions that still describe a live uncategorized item.

        Contract: the id must be one of the ids that were sent, the item must
        still be uncategorized, the category is trimmed, non-empty, not the
        sentinel and at most 40 characters; the reason is trimmed to 200; ids
        are de-duplicated. The item is re-read from the service (not trusted
        from the batch) and its fresh name/target/note are echoed back so the
        UI can apply the suggestion without a stale local copy.
        """
        sent = {item.id: mode for mode, item in batch}
        seen: set[str] = set()
        suggestions: list[dict[str, Any]] = []
        for raw in raw_suggestions:
            if not isinstance(raw, Mapping):
                continue
            raw_id = raw.get("id")
            if not isinstance(raw_id, str) or raw_id in seen:
                continue
            mode = sent.get(raw_id)
            if mode is None:
                continue
            category = raw.get("category")
            if not isinstance(category, str):
                continue
            clean_category = category.strip()
            if (
                not clean_category
                or clean_category == UNCATEGORIZED
                or len(clean_category) > 40
            ):
                continue
            try:
                current = self.state.service.get(mode, raw_id)
            except NotFoundError:
                continue
            if current.category != UNCATEGORIZED:
                continue
            reason = raw.get("reason")
            clean_reason = reason.strip()[:200] if isinstance(reason, str) else ""
            seen.add(raw_id)
            suggestions.append(
                {
                    "mode": mode,
                    "id": raw_id,
                    "name": current.name,
                    "target": current.target,
                    "note": current.note,
                    "currentCategory": current.category,
                    "suggestedCategory": clean_category,
                    "reason": clean_reason,
                }
            )
        return suggestions

    # -- resources ---------------------------------------------------------
    def _list(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        mode = self._require_mode(params)
        labels = params.get("labels")
        labels = labels if isinstance(labels, Mapping) else {}
        query = params.get("query")
        category = params.get("category")
        visible = self.state.service.visible(
            mode,
            query=str(query) if isinstance(query, str) else "",
            category=str(category) if isinstance(category, str) else ALL_CATEGORIES,
            favorites_only=params.get("favoritesOnly") is True,
            uncategorized_label=labels.get("uncategorized"),
            favorite_mark=labels.get("favoriteMark"),
        )
        items = self.state.service.items(mode)
        return {
            "items": [item.to_json() for item in visible],
            "total": len(items),
            "visible": len(visible),
            "categories": list(self.state.service.categories(mode)),
        }

    def _add(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        mode = self._require_mode(params)
        item = self.state.service.add(
            mode,
            name=self._require_str(params, "name"),
            target=self._require_str(params, "target"),
            category=params.get("category") if isinstance(params.get("category"), str) else None,
            note=str(params.get("note") or ""),
            browser=str(params.get("browser") or ""),
        )
        return {"item": item.to_json()}

    def _update(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        mode = self._require_mode(params)
        item = self.state.service.update(
            mode,
            self._require_str(params, "id"),
            name=self._require_str(params, "name"),
            target=self._require_str(params, "target"),
            category=params.get("category") if isinstance(params.get("category"), str) else None,
            note=str(params.get("note") or ""),
            browser=(
                params.get("browser")
                if isinstance(params.get("browser"), str)
                else None
            ),
        )
        return {"item": item.to_json()}

    def _delete(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        mode = self._require_mode(params)
        item_id = self._require_str(params, "id")
        remove_from_browser = params.get("removeFromBrowser") is True
        item = None
        if remove_from_browser and mode == "links":
            # Look the item up first: deleting an unknown id is a no-op, but
            # the extension needs the target of an item that really exists.
            try:
                item = self.state.service.get(mode, item_id)
            except NotFoundError:
                item = None
        deleted = self.state.service.delete(mode, item_id)

        browser_queued = False
        extension_connected = False
        if mode == "links":
            bridge = self.state.bookmark_bridge
            if bridge is not None:
                extension_connected = bridge.connected
                if deleted and remove_from_browser and item is not None:
                    # Queue the exact stored URL: the extension searches its
                    # bookmark tree for it, so a lowercased key could miss a
                    # bookmark whose path contains uppercase characters.
                    bridge.enqueue_remove([item.target])
                    browser_queued = True
        return {
            "deleted": deleted,
            "browserQueued": browser_queued,
            "extensionConnected": extension_connected,
        }

    def _favorite(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        mode = self._require_mode(params)
        item_id = self._require_str(params, "id")
        value = params.get("value")
        if isinstance(value, bool):
            item = self.state.service.set_favorite(mode, item_id, value)
        else:
            item = self.state.service.toggle_favorite(mode, item_id)
        return {"item": item.to_json()}

    def _reorder(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        mode = self._require_mode(params)
        ids = params.get("ids")
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise ProtocolError(
                "bad_request", "params.ids must be an array of strings"
            )
        items = self.state.service.reorder(mode, ids)
        return {"items": [item.to_json() for item in items]}

    def _check_paths(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        mode = self._require_mode(params)
        result = self.state.service.check_paths(mode)
        return {
            "supported": result.supported,
            "total": result.total,
            "missing": list(result.missing),
            "missingCount": result.missing_count,
        }

    def _open(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        mode = self._require_mode(params)
        item = self.state.service.get(mode, self._require_str(params, "id"))
        if mode == "links":
            requested = params.get("browser")
            browser_id = (
                requested.strip()
                if isinstance(requested, str) and requested.strip()
                else getattr(item, "browser", "")
            )
            open_link(
                item.target,
                find_browser(browser_id) if browser_id else None,
            )
        else:
            open_path(item.target)
        return {"opened": True}

    def _reveal(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        mode = self._require_mode(params)
        item = self.state.service.get(mode, self._require_str(params, "id"))
        reveal_path(item.target)
        return {"revealed": True}

    def _drop(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        paths = params.get("paths")
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            raise ProtocolError("bad_request", "params.paths must be an array of strings")
        result = self.state.service.add_dropped(paths)
        return {
            "added": result.added,
            "skipped": result.skipped,
            "invalid": result.invalid,
        }

    def _export(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        mode = self._require_mode(params)
        return {"items": self.state.service.export_payload(mode)}

    def _import(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_loaded()
        mode = self._require_mode(params)
        items = params.get("items")
        if not isinstance(items, list):
            raise ProtocolError("bad_request", "params.items must be an array")
        result = self.state.service.import_payload(mode, items)
        return {"imported": result.imported, "skipped": result.skipped}

    # -- filesystem browsing (preview panel, read-only) --------------------
    def _fs_children(self, params: Mapping[str, Any]) -> dict[str, Any]:
        path = self._require_str(params, "path")
        listing = list_children(path)
        return {
            "path": listing.path,
            "entries": [entry.to_json() for entry in listing.entries],
            "total": listing.total,
            "shown": listing.shown,
            "truncated": listing.truncated,
        }

    def _fs_open(self, params: Mapping[str, Any]) -> dict[str, Any]:
        open_fs_path(self._require_str(params, "path"))
        return {"opened": True}

    def _fs_reveal(self, params: Mapping[str, Any]) -> dict[str, Any]:
        reveal_fs_path(self._require_str(params, "path"))
        return {"revealed": True}

    # -- settings ----------------------------------------------------------
    def _settings_get(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return {"settings": self.state.settings.to_json()}

    def _settings_set(self, params: Mapping[str, Any]) -> dict[str, Any]:
        raw = params.get("settings")
        if not isinstance(raw, Mapping):
            raise ProtocolError("bad_request", "params.settings must be an object")
        settings = Settings.normalize(raw)
        self.state.settings_store.save(settings)
        self.state.settings = settings
        return {"settings": settings.to_json()}

    def _probe_hotkey(self, params: Mapping[str, Any]) -> dict[str, Any]:
        hotkey_id = self._require_str(params, "hotkeyId")
        return {"available": is_combination_available(hotkey_id)}

    # -- hotkey ------------------------------------------------------------
    def _hotkey_pressed(self, action: str) -> Callable[[], None]:
        """Build the ``on_press`` callback for one hotkey ``action``."""
        return lambda: self.writer.event("hotkey", {"action": action})

    def _hotkey_start(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self.stop_hotkey()
        settings = self.state.settings
        targets = (
            ("toggle", settings.global_hotkey_id),
            ("quickLinks", settings.quick_links_hotkey_id),
            ("quickFolders", settings.quick_folders_hotkey_id),
        )
        registrations: list[dict[str, Any]] = []
        toggle_label = settings.global_hotkey_id
        toggle_registered = False
        if settings.global_hotkey_enabled:
            # One listener per action: three message pumps are independent
            # because each registers with hWnd NULL on its own thread.
            for action, label in targets:
                listener = GlobalHotkeyListener(label, self._hotkey_pressed(action))
                registered = listener.start()
                if registered:
                    self.state.hotkey.append(listener)
                    if action == "toggle":
                        toggle_label = listener.active_label
                        toggle_registered = True
                registrations.append(
                    {
                        "action": action,
                        "label": listener.active_label,
                        "registered": registered,
                        "reason": None if registered else "unavailable",
                    }
                )
        else:
            registrations = [
                {
                    "action": action,
                    "label": label,
                    "registered": False,
                    "reason": "disabled",
                }
                for action, label in targets
            ]

        # Mouse side buttons are a separate opt-in switch: they keep working
        # when the keyboard hotkeys are disabled.
        mouse_registered = False
        if settings.mouse_side_buttons_enabled:
            mouse = MouseSideButtonListener(
                lambda action: self._hotkey_pressed(action)()
            )
            mouse_registered = mouse.start()
            if mouse_registered:
                self.state.mouse_hook = mouse

        return {
            "registered": toggle_registered,
            "label": toggle_label,
            "reason": None
            if toggle_registered
            else ("unavailable" if settings.global_hotkey_enabled else "disabled"),
            "registrations": registrations,
            "mouseSideButtons": {
                "enabled": settings.mouse_side_buttons_enabled,
                "registered": mouse_registered,
                "reason": None
                if mouse_registered
                else (
                    "unavailable"
                    if settings.mouse_side_buttons_enabled
                    else "disabled"
                ),
            },
        }

    def _hotkey_stop(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self.stop_hotkey()
        return {"stopped": True}

    def stop_hotkey(self) -> None:
        for listener in self.state.hotkey:
            listener.stop()
        self.state.hotkey.clear()
        mouse = self.state.mouse_hook
        self.state.mouse_hook = None
        if mouse is not None:
            mouse.stop()

    def stop_bookmarks(self) -> None:
        """Stop the watcher thread (safe to call more than once)."""
        watcher = self.state.bookmark_watcher
        self.state.bookmark_watcher = None
        if watcher is not None:
            watcher.stop()

    def stop_bridge(self) -> None:
        """Stop the loopback extension bridge (safe to call more than once)."""
        bridge = self.state.bookmark_bridge
        self.state.bookmark_bridge = None
        if bridge is not None:
            bridge.stop()


class JsonLinesServer:
    """Reads requests from ``in_stream``, writes frames to ``out_stream``."""

    def __init__(
        self,
        base_dir: Path,
        *,
        in_stream: IO[str],
        out_stream: IO[str],
        load: bool = True,
    ) -> None:
        self.base_dir = Path(base_dir)
        self._in = in_stream
        self.writer = FrameWriter(out_stream)
        self._stop_requested = False

        service = ResourceService(self.base_dir)
        load_error: str | None = None
        if load:
            try:
                service.load()
            except CorruptDataError as exc:
                # Do not touch the files; surface the problem to the UI instead.
                load_error = exc.detail
        self.state = ServerState(
            base_dir=self.base_dir,
            service=service,
            settings_store=SettingsStore(self.base_dir / "settings.json"),
            settings=Settings(),
            bookmark_engine=BookmarkSyncEngine(self.base_dir),
            ai_key_store=AiKeyStore(self.base_dir / AI_KEY_FILENAME),
            favicons=FaviconStore(self.base_dir),
            load_error=load_error,
        )
        if load_error is None:
            self.state.settings = self.state.settings_store.load()
        self.dispatcher = Dispatcher(self.state, self.writer)

    # -- loop --------------------------------------------------------------
    def serve_forever(self) -> int:
        self._start_bookmarks()
        self._start_bridge()
        try:
            for raw_line in self._in:
                line = raw_line.strip()
                if not line:
                    continue
                self._handle_line(line)
                if self._stop_requested:
                    break
        finally:
            # Reached both after app.shutdown and on stdin EOF.
            self._shutdown()
        return 0

    def _start_bookmarks(self) -> None:
        """Import existing bookmarks once, then watch the files for changes."""
        state = self.state
        if state.load_error is not None or state.bookmark_watcher is not None:
            return
        # First-run / every-start reconciliation happens before the first
        # request is served, so the very first `resources.list` already contains
        # the imported bookmarks (and bookmarks added while the app was closed).
        # Failures are non-fatal: a missing/odd browser profile must not stop the
        # backend from starting.
        if state.settings.bookmark_sync_enabled:
            try:
                with state.bookmark_lock:
                    imported = state.bookmark_engine.sync(
                        state.service, state.settings
                    )
                if imported["added"] > 0:
                    self.writer.event(
                        "bookmarks", bookmark_event_payload(imported)
                    )
            except Exception:  # noqa: BLE001 - best-effort startup import
                pass
        watcher = BookmarkWatcher(
            state.bookmark_engine,
            state.service,
            lambda: state.settings,
            lambda result: self.writer.event(
                "bookmarks", bookmark_event_payload(result)
            ),
            lock=state.bookmark_lock,
        )
        state.bookmark_watcher = watcher
        watcher.start()

    def _start_bridge(self) -> None:
        """Start the loopback HTTP bridge the browser extension polls (Phase 18).

        Corrupt data files mean the service cannot be mutated, so the bridge is
        not started: reverse-sync events would have nothing safe to act on. A
        bind failure is not fatal either — bookmark import keeps working, the UI
        simply reports the extension as unreachable.
        """
        state = self.state
        if state.load_error is not None or state.bookmark_bridge is not None:
            return
        bridge = BookmarkBridge(
            state.service,
            state.bookmark_engine,
            writer=self.writer,
            lock=state.bookmark_lock,
        )
        if bridge.start():
            state.bookmark_bridge = bridge

    def _handle_line(self, line: str) -> bool:
        try:
            frame = json.loads(line)
        except json.JSONDecodeError as exc:
            self.writer.error(
                None, ProtocolError("bad_request", f"invalid JSON: {exc.msg}")
            )
            return True
        if not isinstance(frame, Mapping):
            self.writer.error(None, ProtocolError("bad_request", "frame must be an object"))
            return True

        request_id = frame.get("id")
        method = frame.get("method")
        params = frame.get("params") or {}
        if not isinstance(method, str):
            self.writer.error(request_id, ProtocolError("bad_request", "missing method"))
            return True
        if not isinstance(params, Mapping):
            self.writer.error(
                request_id, ProtocolError("bad_request", "params must be an object")
            )
            return True

        try:
            result = self.dispatcher.dispatch(method, params)
        except ProtocolError as exc:
            self.writer.error(request_id, exc)
        except (ValidationError, DuplicateError, NotFoundError) as exc:
            code = (
                "validation" if isinstance(exc, ValidationError)
                else "duplicate" if isinstance(exc, DuplicateError)
                else "not_found"
            )
            self.writer.error(request_id, ProtocolError(code, exc.detail, key=exc.key))
        except CorruptDataError as exc:
            self.writer.error(
                request_id, ProtocolError("corrupt_data", exc.detail, key="data_corrupt")
            )
        except ServiceError as exc:
            # An expected failure (missing path, bad backup) — one line, no trace.
            print(
                f"[resource-hub] {method}: {exc.key or type(exc).__name__}: {exc.detail}",
                file=sys.stderr,
            )
            self.writer.error(
                request_id,
                ProtocolError("operation_failed", exc.detail, key=exc.key),
            )
        except Exception as exc:  # noqa: BLE001 - a handler must never kill the loop
            # Swallowing this without a trace would hide real bugs (an early
            # AttributeError in app.shutdown was masked exactly this way).
            self._log_internal(method, exc)
            self.writer.error(
                request_id, ProtocolError("internal", f"{type(exc).__name__}: {exc}")
            )
        else:
            self.writer.response(request_id, result)
            if method == "app.shutdown":
                self._stop_requested = True
        return True

    def _shutdown(self) -> None:
        self.dispatcher.stop_bridge()
        self.dispatcher.stop_hotkey()
        self.dispatcher.stop_bookmarks()

    @staticmethod
    def _log_internal(method: str, exc: BaseException) -> None:
        """Diagnostics go to stderr; stdout carries protocol frames only."""
        print(f"[resource-hub] {method} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)


def configure_stdio() -> None:
    """Force UTF-8 on Windows (the default cp936 mangles Chinese paths)."""
    reconfigure_in = getattr(sys.stdin, "reconfigure", None)
    if reconfigure_in is not None:
        reconfigure_in(encoding="utf-8", errors="replace")
    reconfigure_out = getattr(sys.stdout, "reconfigure", None)
    if reconfigure_out is not None:
        # newline="\n" keeps frames LF-terminated instead of CRLF on Windows.
        reconfigure_out(encoding="utf-8", errors="replace", newline="\n")
