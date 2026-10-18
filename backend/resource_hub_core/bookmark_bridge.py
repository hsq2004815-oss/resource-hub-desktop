"""Loopback HTTP bridge between the browser extension and the backend (Phase 18).

Phase 17 already imports Chrome/Edge bookmarks: the backend reads the browser
``Bookmarks`` files and the watcher picks up additions. That bridge is one-way
and pull-only — a resource deleted in the tool stays in the browser, and a
bookmark deleted or renamed in the browser is never reflected back.

This module adds the other direction. A tiny HTTP server binds to
``127.0.0.1`` on the first free port in 47821..47830 (port 0 as a last resort so
tests and odd installs still work) and the bundled Manifest V3 extension polls
it. Nothing outside the loopback interface can connect, browser files are still
never written, and every request handler is exception-safe: a malformed plugin
request must never take the backend down.

Endpoints (JSON, with CORS headers because the extension service worker is a
different origin; ``OPTIONS`` answers 204)::

    GET  /ping      -> {"app": "resource-hub", "protocol": 1}
    GET  /commands  -> {"commands": [{"id", "op": "remove", "urls",
                                     "createdAt"}]}
    POST /ack       <- {"results": [{"id": "…", "removed": n, "failed": m}]}
                       -> {"ok": true}
    POST /events    <- {"events": [{"type": "removed", "url": "…"},
                                   {"type": "changed", "url": "…",
                                    "title": "…"}]}
                       -> {"ok": true, "deleted": n, "renamed": m}

Unknown paths answer 404, malformed JSON bodies 400; both as JSON.

Command queue
-------------
Deleting a link with ``removeFromBrowser`` queues one ``remove`` command. The
extension polls ``/commands``, removes the browser bookmarks and acknowledges
them on ``/ack`` (the counts are informational — the backend only forgets the
ids). Commands expire after ten minutes so a stale queued removal cannot delete
a bookmark the user re-created in the browser in the meantime.

Reverse sync
------------
A ``removed`` event deletes the matching link resource(s) and forgets the URL in
the ``seenUrls`` ledger, so re-bookmarking the same URL later imports it again.
A ``changed`` event renames the matching link resource(s). Events are applied in
order under the server's bookmark lock; duplicate or unrelated URLs are no-ops.
One ``{"event": "bookmarks", …}`` frame is written per batch that changed
something, which every open window uses to refresh its list.

Threading
---------
The HTTP server runs on its own daemon thread and the request handlers on
daemon threads owned by :class:`ThreadingHTTPServer`. Service and metadata
mutations take the same ``RLock`` the protocol dispatcher and the file watcher
use, so an extension event can never interleave with a protocol write.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlsplit

from .bookmarks import BookmarkSyncEngine, dedup_key
from .models import Resource
from .normalize import now_iso
from .service import ResourceService, ServiceError

#: The only address the bridge ever listens on.
BRIDGE_HOST = "127.0.0.1"

#: Preferred ports; 47821 is the one the extension probes first.
BRIDGE_PORTS: tuple[int, ...] = tuple(range(47821, 47831))

#: Protocol version reported by ``/ping``; the extension refuses other values.
BRIDGE_PROTOCOL_VERSION = 1

#: The extension counts as connected while it has polled within this window.
CONNECTED_WINDOW_SECONDS = 15.0

#: A queued command older than this is dropped instead of executed late.
COMMAND_TTL_SECONDS = 600.0

#: Refuse bodies larger than this. The extension buffers at most 500 events,
#: which stays comfortably below it; the limit only protects the backend from a
#: malformed client on the loopback interface.
MAX_BODY_BYTES = 256 * 1024

_REMOVE_OP = "remove"

_CORS_HEADERS: tuple[tuple[str, str], ...] = (
    ("Access-Control-Allow-Origin", "*"),
    ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
    ("Access-Control-Allow-Headers", "Content-Type"),
)


class BridgeWriter(Protocol):
    """What the bridge needs from ``FrameWriter``, kept protocol-agnostic."""

    def event(self, name: str, payload: Mapping[str, Any] | None = None) -> None: ...


@dataclass(frozen=True, slots=True)
class PendingCommand:
    """One browser operation waiting for the extension to poll it."""

    id: str
    op: str
    urls: tuple[str, ...]
    created_at: str
    #: ``time.monotonic()`` deadline; wall-clock time cannot jump past it.
    expires_at: float

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "op": self.op,
            "urls": list(self.urls),
            "createdAt": self.created_at,
        }


class BookmarkBridge:
    """The loopback endpoint the extension talks to.

    Owns the HTTP server, the pending-command queue and the reverse sync. It is
    created and stopped by :class:`resource_hub_core.protocol.JsonLinesServer`;
    tests may drive it directly.
    """

    def __init__(
        self,
        service: ResourceService,
        engine: BookmarkSyncEngine,
        writer: BridgeWriter | None = None,
        lock: threading.RLock | None = None,
        *,
        ports: Sequence[int] = BRIDGE_PORTS,
        command_ttl: float = COMMAND_TTL_SECONDS,
        connected_window: float = CONNECTED_WINDOW_SECONDS,
    ) -> None:
        self._service = service
        self._engine = engine
        self._writer = writer
        self._lock = lock
        self._ports = tuple(int(port) for port in ports)
        self._command_ttl = max(0.0, float(command_ttl))
        self._connected_window = max(0.0, float(connected_window))

        self._commands: dict[str, PendingCommand] = {}
        self._commands_lock = threading.Lock()

        self._last_seen: float | None = None  # monotonic stamp
        self._last_seen_iso: str | None = None

        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> bool:
        """Bind the first free loopback port and serve on a daemon thread.

        Returns ``False`` when no port could be bound at all (the bookmark
        import still works, only the extension stops working).
        """
        if self._server is not None:
            return True
        server = self._bind_server()
        if server is None:
            return False
        self._server = server
        self._thread = threading.Thread(
            # A short poll interval keeps stop() prompt: shutdown() has to wait
            # for the serve loop's select() to time out, and the test suite
            # starts/stops a bridge for every protocol server. Ten idle wakeups
            # per second are nothing for one loopback listener.
            target=lambda: server.serve_forever(poll_interval=0.01),
            name="bookmark-bridge",
            daemon=True,
        )
        self._thread.start()
        return True

    def _bind_server(self) -> ThreadingHTTPServer | None:
        handler = _make_handler(self)
        # Port 0 is the documented fallback: an ephemeral port still lets the
        # extension work as long as it can discover it, and keeps tests running
        # on a machine where the whole preferred range is taken.
        for port in (*self._ports, 0):
            try:
                return _BridgeHTTPServer((BRIDGE_HOST, port), handler)
            except OSError:
                continue
        return None

    @property
    def port(self) -> int | None:
        """The bound port, or ``None`` while stopped / never started."""
        server = self._server
        return None if server is None else int(server.server_address[1])

    @property
    def running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def stop(self) -> None:
        """Stop serving and close the port. Safe to call more than once."""
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            try:
                server.shutdown()
            except Exception:  # noqa: BLE001 - shutdown must never raise
                pass
            try:
                server.server_close()
            except OSError:
                pass
        if thread is not None:
            thread.join(2.0)

    # -- extension presence ------------------------------------------------
    def _mark_seen(self) -> None:
        """Record that the extension is alive (called by every HTTP request)."""
        self._last_seen = time.monotonic()
        self._last_seen_iso = now_iso()

    @property
    def last_seen(self) -> float | None:
        """``time.monotonic()`` stamp of the last request, if there was one."""
        return self._last_seen

    @property
    def last_seen_iso(self) -> str | None:
        """Wall-clock ISO-8601 stamp of the last request, for ``lastSeenAt``."""
        return self._last_seen_iso

    @property
    def connected(self) -> bool:
        """True while the extension has polled recently enough."""
        seen = self._last_seen
        return seen is not None and time.monotonic() - seen < self._connected_window

    # -- command queue -----------------------------------------------------
    def _drop_expired(self) -> None:
        now = time.monotonic()
        expired = [
            command_id
            for command_id, command in self._commands.items()
            if command.expires_at <= now
        ]
        for command_id in expired:
            self._commands.pop(command_id, None)

    def enqueue_remove(self, urls: Sequence[str]) -> str:
        """Queue one ``remove`` command and return its id."""
        cleaned = tuple(str(url).strip() for url in urls if str(url).strip())
        command = PendingCommand(
            id=uuid.uuid4().hex,
            op=_REMOVE_OP,
            urls=cleaned,
            created_at=now_iso(),
            expires_at=time.monotonic() + self._command_ttl,
        )
        with self._commands_lock:
            self._drop_expired()
            self._commands[command.id] = command
        return command.id

    def pending_commands(self) -> list[PendingCommand]:
        """Unexpired commands in enqueue order (expired ones are dropped)."""
        with self._commands_lock:
            self._drop_expired()
            return list(self._commands.values())

    def pending_count(self) -> int:
        return len(self.pending_commands())

    def acknowledge(self, results: Any) -> None:
        """Forget acknowledged commands; unknown ids and shapes are ignored."""
        if not isinstance(results, list):
            return
        with self._commands_lock:
            for entry in results:
                if isinstance(entry, Mapping) and isinstance(entry.get("id"), str):
                    self._commands.pop(entry["id"], None)

    # -- reverse sync ------------------------------------------------------
    def apply_events(self, events: Any) -> tuple[int, int]:
        """Apply a browser event batch, returning ``(deleted, renamed)``.

        The whole batch is applied under the shared bookmark lock, so it can
        never interleave with a protocol write or a watcher sync. One
        ``bookmarks`` writer event is emitted when anything changed.
        """
        if not isinstance(events, list) or not events:
            return 0, 0
        if self._lock is not None:
            with self._lock:
                deleted, renamed = self._apply_events_locked(events)
        else:
            deleted, renamed = self._apply_events_locked(events)
        if (deleted or renamed) and self._writer is not None:
            # Mirrors the import event, plus the two reverse counters the UI
            # needs for its "changed by the browser" snackbars.
            self._writer.event(
                "bookmarks",
                {
                    "added": 0,
                    "deleted": deleted,
                    "renamed": renamed,
                    "lastSyncAt": now_iso(),
                },
            )
        return deleted, renamed

    def _apply_events_locked(self, events: Sequence[Any]) -> tuple[int, int]:
        seen = self._engine.seen_urls()
        forgotten: set[str] = set()
        deleted = 0
        renamed = 0
        for raw in events:
            if not isinstance(raw, Mapping):
                continue
            url = raw.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            event_type = raw.get("type")
            if event_type == "removed":
                key = dedup_key(url)
                if key not in seen:
                    continue
                for item in self._links_matching(key):
                    if self._service.delete("links", item.id):
                        deleted += 1
                # Forget the URL even when no resource matched: the browser
                # bookmark is gone, so a later re-bookmark must import again.
                seen.discard(key)
                forgotten.add(key)
            elif event_type == "changed":
                key = dedup_key(url)
                title = raw.get("title")
                if key not in seen or not isinstance(title, str) or not title.strip():
                    continue
                clean_title = title.strip()
                for item in self._links_matching(key):
                    if item.name == clean_title:
                        continue
                    try:
                        # Only the name changes: the target is the identity, and
                        # category/note/favourite/createdAt come from the item.
                        self._service.update(
                            "links",
                            item.id,
                            name=clean_title,
                            target=item.target,
                            category=item.category,
                            note=item.note,
                        )
                    except ServiceError:
                        continue
                    renamed += 1
        if forgotten:
            self._engine.forget_seen(forgotten)
        return deleted, renamed

    def _links_matching(self, key: str) -> tuple[Resource, ...]:
        """Link resources whose target has the same normalized URL."""
        return tuple(
            item
            for item in self._service.items("links")
            if dedup_key(item.target) == key
        )


# --- HTTP plumbing ---------------------------------------------------------
class _BridgeHTTPServer(ThreadingHTTPServer):
    """Loopback-only server whose handler threads never block shutdown."""

    daemon_threads = True
    # Windows' SO_REUSEADDR lets a second process bind a port that is already
    # being listened on, so two bridges would silently share 47821 and requests
    # would hit the wrong (or the running app's) queue. Refuse to reuse instead:
    # the start loop then falls through to the next free port.
    allow_reuse_address = False


_INVALID_JSON = object()


def _make_handler(bridge: BookmarkBridge) -> type[BaseHTTPRequestHandler]:
    """Build the request handler class bound to ``bridge``.

    A closure instead of a module-level singleton keeps two bridges in one
    process (e.g. two tests, or two app instances) independent.
    """

    class _BridgeHandler(BaseHTTPRequestHandler):
        server_version = "ResourceHubBridge/1"
        sys_version = ""

        # BaseHTTPRequestHandler logs every request to stderr; the extension
        # polls every 1.5 s, so the protocol streams stay quiet instead.
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass

        # -- routing ---------------------------------------------------
        def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib naming
            self._send(204, None)

        def do_GET(self) -> None:  # noqa: N802 - stdlib naming
            path = urlsplit(self.path).path
            if path == "/ping":
                bridge._mark_seen()
                self._send(
                    200,
                    {"app": "resource-hub", "protocol": BRIDGE_PROTOCOL_VERSION},
                )
                return
            if path == "/commands":
                bridge._mark_seen()
                self._send(
                    200,
                    {
                        "commands": [
                            command.to_json()
                            for command in bridge.pending_commands()
                        ]
                    },
                )
                return
            self._send(404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802 - stdlib naming
            path = urlsplit(self.path).path
            if path not in ("/ack", "/events"):
                self._send(404, {"ok": False, "error": "not_found"})
                return
            payload = self._read_json()
            if payload is _INVALID_JSON:
                self._send(400, {"ok": False, "error": "invalid_json"})
                return
            if not isinstance(payload, Mapping):
                self._send(400, {"ok": False, "error": "bad_request"})
                return
            bridge._mark_seen()
            if path == "/ack":
                bridge.acknowledge(payload.get("results"))
                self._send(200, {"ok": True})
                return
            try:
                deleted, renamed = bridge.apply_events(payload.get("events"))
            except Exception:  # noqa: BLE001 - one bad request must not kill it
                self._send(500, {"ok": False, "error": "internal"})
                return
            self._send(200, {"ok": True, "deleted": deleted, "renamed": renamed})

        # -- response helpers ------------------------------------------
        def _send(self, status: int, payload: Mapping[str, Any] | None) -> None:
            if payload is None:
                body = b""
            else:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            for name, value in _CORS_HEADERS:
                self.send_header(name, value)
            if payload is not None:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _read_json(self) -> Any:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                return _INVALID_JSON
            if length <= 0 or length > MAX_BODY_BYTES:
                return _INVALID_JSON
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return _INVALID_JSON

    return _BridgeHandler
