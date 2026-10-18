"""Tests for the loopback HTTP bridge the browser extension talks to (Phase 18).

Like the Phase 17 tests, bookmark discovery is pinned through
``RH_BROWSER_DATA_DIRS`` to a temporary fixture, so the developer's real Chrome
and Edge profiles are never read. The bridge itself only ever binds 127.0.0.1;
the HTTP client here talks to that port exactly the way the extension does.
"""

from __future__ import annotations

import http.client
import io
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from resource_hub_core.bookmark_bridge import (
    BRIDGE_PROTOCOL_VERSION,
    BookmarkBridge,
)
from resource_hub_core.bookmarks import (
    BROWSER_DATA_DIRS_ENV,
    BookmarkSyncEngine,
)
from resource_hub_core.protocol import FrameWriter
from resource_hub_core.service import ORDER_META_FILENAME, ResourceService
from resource_hub_core.settings import Settings


def write_profile(root: Path, entries: list[tuple[str, str]]) -> Path:
    """Write a minimal Chrome-style ``Bookmarks`` file under ``root/Default``."""
    directory = root / "Default"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "Bookmarks"
    payload = {
        "roots": {
            "bookmark_bar": {
                "type": "folder",
                "name": "Bookmarks bar",
                "children": [
                    {"type": "url", "name": name, "url": url}
                    for name, url in entries
                ],
            }
        }
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class BridgeFixtureTestCase(unittest.TestCase):
    """A loaded service, a sync engine and a started bridge on a temp data dir."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.app_dir = self.base / "app"
        self.browser_root = self.base / "browser"
        self._env = mock.patch.dict(
            os.environ, {BROWSER_DATA_DIRS_ENV: str(self.browser_root)}
        )
        self._env.start()

        self.service = ResourceService(self.app_dir)
        self.service.load()
        self.engine = BookmarkSyncEngine(self.app_dir)
        self.settings = Settings()
        self.out = io.StringIO()
        self.writer = FrameWriter(self.out)
        self.lock = threading.RLock()
        self.bridge = BookmarkBridge(
            self.service,
            self.engine,
            writer=self.writer,
            lock=self.lock,
        )
        self.assertTrue(self.bridge.start(), "bridge could not bind a loopback port")

    def tearDown(self) -> None:
        self.bridge.stop()
        self._env.stop()
        self._tmp.cleanup()

    # -- helpers -----------------------------------------------------------
    def sync(self) -> dict[str, Any]:
        with self.lock:
            return self.engine.sync(self.service, self.settings)

    def request(
        self, method: str, path: str, payload: Any = None
    ) -> tuple[int, dict[str, Any]]:
        """One extension-style HTTP call against the fixture bridge."""
        return http_json(self.bridge.port or 0, method, path, payload)

    def meta(self) -> dict[str, Any]:
        return json.loads(
            (self.app_dir / ORDER_META_FILENAME).read_text(encoding="utf-8")
        )

    def writer_frames(self) -> list[dict[str, Any]]:
        return [
            json.loads(line) for line in self.out.getvalue().splitlines() if line
        ]


def http_json(
    port: int, method: str, path: str, payload: Any = None
) -> tuple[int, dict[str, Any]]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False)
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        return response.status, (json.loads(raw.decode("utf-8")) if raw else {})
    finally:
        connection.close()


# --- endpoints -------------------------------------------------------------
class BridgeEndpointTests(BridgeFixtureTestCase):
    def test_ping_reports_the_contract_and_marks_the_extension_alive(self) -> None:
        self.assertFalse(self.bridge.connected)
        self.assertIsNone(self.bridge.last_seen)

        status, payload = self.request("GET", "/ping")

        self.assertEqual(status, 200)
        self.assertEqual(
            payload, {"app": "resource-hub", "protocol": BRIDGE_PROTOCOL_VERSION}
        )
        self.assertTrue(self.bridge.connected)
        self.assertIsInstance(self.bridge.last_seen, float)
        self.assertIsInstance(self.bridge.last_seen_iso, str)

    def test_cors_headers_and_options_preflight(self) -> None:
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.bridge.port, timeout=5
        )
        try:
            connection.request("OPTIONS", "/commands")
            response = connection.getresponse()
            self.assertEqual(response.read(), b"")
            self.assertEqual(response.status, 204)
            self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
            self.assertIn(
                "POST",
                response.getheader("Access-Control-Allow-Methods") or "",
            )
            self.assertEqual(
                response.getheader("Access-Control-Allow-Headers"), "Content-Type"
            )
        finally:
            connection.close()

    def test_json_responses_carry_cors_headers(self) -> None:
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.bridge.port, timeout=5
        )
        try:
            connection.request("GET", "/ping")
            response = connection.getresponse()
            response.read()
            self.assertEqual(
                response.getheader("Access-Control-Allow-Origin"), "*"
            )
        finally:
            connection.close()

    def test_unknown_path_is_a_json_404(self) -> None:
        for method, payload in (("GET", None), ("POST", {})):
            with self.subTest(method=method):
                status, body = self.request(method, "/nope", payload)
                self.assertEqual(status, 404)
                self.assertFalse(body["ok"])

    def test_malformed_json_body_is_a_json_400(self) -> None:
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.bridge.port, timeout=5
        )
        try:
            connection.request(
                "POST",
                "/events",
                body="{not json",
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            body = json.loads(response.read().decode("utf-8"))
            self.assertFalse(body["ok"])
            self.assertEqual(body["error"], "invalid_json")
        finally:
            connection.close()

    def test_a_non_object_json_body_is_a_400(self) -> None:
        status, body = self.request("POST", "/ack", [1, 2])
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])

    def test_stop_closes_the_port_and_is_idempotent(self) -> None:
        port = self.bridge.port
        self.assertIsInstance(port, int)
        self.assertTrue(self.bridge.running)

        self.bridge.stop()
        self.bridge.stop()  # idempotent

        self.assertIsNone(self.bridge.port)
        self.assertFalse(self.bridge.running)
        with self.assertRaises(OSError):
            http_json(port or 0, "GET", "/ping")

    def test_falls_back_to_an_ephemeral_port_when_the_preferred_one_is_busy(
        self,
    ) -> None:
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        busy_port = holder.getsockname()[1]
        bridge = BookmarkBridge(self.service, self.engine, ports=(busy_port,))
        try:
            self.assertTrue(bridge.start())
            self.assertIsInstance(bridge.port, int)
            self.assertNotEqual(bridge.port, busy_port)
            self.assertEqual(
                http_json(bridge.port or 0, "GET", "/ping")[1]["app"],
                "resource-hub",
            )
        finally:
            bridge.stop()
            holder.close()


# --- command queue ---------------------------------------------------------
class CommandQueueTests(BridgeFixtureTestCase):
    def test_enqueue_poll_and_ack_roundtrip(self) -> None:
        command_id = self.bridge.enqueue_remove(["https://a.example/"])
        self.assertEqual(self.bridge.pending_count(), 1)

        status, payload = self.request("GET", "/commands")

        self.assertEqual(status, 200)
        commands = payload["commands"]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["id"], command_id)
        self.assertEqual(commands[0]["op"], "remove")
        self.assertEqual(commands[0]["urls"], ["https://a.example/"])
        self.assertIsInstance(commands[0]["createdAt"], str)
        # Polling is what marks the extension connected.
        self.assertTrue(self.bridge.connected)

        status, payload = self.request(
            "POST",
            "/ack",
            {"results": [{"id": command_id, "removed": 1, "failed": 0}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(self.bridge.pending_count(), 0)
        self.assertEqual(self.request("GET", "/commands")[1], {"commands": []})

    def test_ack_ignores_unknown_ids_and_malformed_results(self) -> None:
        self.bridge.enqueue_remove(["https://a.example/"])

        self.request(
            "POST", "/ack", {"results": [{"id": "not-a-command", "removed": 0}]}
        )
        self.assertEqual(self.bridge.pending_count(), 1)

        self.request("POST", "/ack", {})
        self.request("POST", "/ack", {"results": "nope"})
        self.assertEqual(self.bridge.pending_count(), 1)

    def test_commands_expire_after_their_ttl(self) -> None:
        bridge = BookmarkBridge(self.service, self.engine, command_ttl=0.01)
        self.assertTrue(bridge.start())
        try:
            bridge.enqueue_remove(["https://expired.example/"])
            self.assertEqual(bridge.pending_count(), 1)
            time.sleep(0.05)
            self.assertEqual(bridge.pending_commands(), [])
            self.assertEqual(bridge.pending_count(), 0)
            self.assertEqual(http_json(bridge.port or 0, "GET", "/commands")[1],
                             {"commands": []})
        finally:
            bridge.stop()

    def test_empty_urls_are_filtered_out_of_a_command(self) -> None:
        self.bridge.enqueue_remove(["  ", "https://a.example/"])
        commands = self.bridge.pending_commands()
        self.assertEqual(commands[0].urls, ("https://a.example/",))


# --- reverse sync ----------------------------------------------------------
class ReverseSyncTests(BridgeFixtureTestCase):
    def _import(self, entries: list[tuple[str, str]]) -> Path:
        path = write_profile(self.browser_root, entries)
        result = self.sync()
        self.assertEqual(result["added"], len(entries))
        return path

    def _link(self, name: str) -> Any:
        return next(item for item in self.service.items("links") if item.name == name)

    def test_removed_event_deletes_the_resource_and_prunes_seen(self) -> None:
        path = self._import([("Home", "https://home.example/")])
        home = self._link("Home")
        self.assertEqual(self.meta()["bookmarks"]["seenUrls"], ["https://home.example"])
        browser_before = path.read_bytes()

        status, payload = self.request(
            "POST",
            "/events",
            {"events": [{"type": "removed", "url": "https://home.example/"}]},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True, "deleted": 1, "renamed": 0})
        self.assertNotIn(home.id, [item.id for item in self.service.items("links")])
        # The seen ledger forgets the URL, but keeps the order migration marker.
        meta = self.meta()
        self.assertEqual(meta["bookmarks"]["seenUrls"], [])
        self.assertEqual(meta["orderVersion"], 1)
        # The browser file is still read-only.
        self.assertEqual(path.read_bytes(), browser_before)

        # The bookmark still exists in the browser: the next sync imports it.
        result = self.sync()
        self.assertEqual(result["added"], 1)
        self.assertEqual(self._link("Home").url, "https://home.example/")

        frames = self.writer_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["event"], "bookmarks")
        payload = frames[0]["payload"]
        self.assertEqual(
            (payload["added"], payload["deleted"], payload["renamed"]),
            (0, 1, 0),
        )
        self.assertIsInstance(payload["lastSyncAt"], str)

    def test_duplicate_removed_events_count_once(self) -> None:
        self._import([("Home", "https://home.example/")])

        status, payload = self.request(
            "POST",
            "/events",
            {
                "events": [
                    {"type": "removed", "url": "https://home.example/"},
                    {"type": "removed", "url": "https://HOME.example"},
                ]
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["deleted"], 1)
        self.assertEqual(self.meta()["bookmarks"]["seenUrls"], [])

    def test_removed_event_for_an_unrelated_url_is_a_noop(self) -> None:
        self._import([("Home", "https://home.example/")])
        before = [item.id for item in self.service.items("links")]

        status, payload = self.request(
            "POST",
            "/events",
            {"events": [{"type": "removed", "url": "https://unrelated.example/"}]},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True, "deleted": 0, "renamed": 0})
        self.assertEqual([item.id for item in self.service.items("links")], before)
        self.assertEqual(self.writer_frames(), [])

    def test_changed_event_renames_and_preserves_every_other_field(self) -> None:
        self._import([("Home", "https://home.example/")])
        home = self._link("Home")
        self.service.set_favorite("links", home.id, True)

        status, payload = self.request(
            "POST",
            "/events",
            {
                "events": [
                    {
                        "type": "changed",
                        "url": "https://home.example/",
                        "title": "  Home (renamed)  ",
                    }
                ]
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True, "deleted": 0, "renamed": 1})
        updated = next(
            item for item in self.service.items("links") if item.id == home.id
        )
        self.assertEqual(updated.name, "Home (renamed)")
        self.assertEqual(updated.target, "https://home.example/")
        self.assertEqual(updated.category, home.category)
        self.assertEqual(updated.note, home.note)
        self.assertEqual(updated.created_at, home.created_at)
        self.assertTrue(updated.favorite)

        frames = self.writer_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["payload"]["renamed"], 1)
        self.assertEqual(frames[0]["payload"]["deleted"], 0)

    def test_changed_event_to_the_same_title_is_a_noop(self) -> None:
        self._import([("Home", "https://home.example/")])

        status, payload = self.request(
            "POST",
            "/events",
            {
                "events": [
                    {"type": "changed", "url": "https://home.example/", "title": "Home"}
                ]
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["renamed"], 0)
        self.assertEqual(self.writer_frames(), [])

    def test_changed_event_for_an_unrelated_url_is_a_noop(self) -> None:
        self._import([("Home", "https://home.example/")])

        status, payload = self.request(
            "POST",
            "/events",
            {
                "events": [
                    {
                        "type": "changed",
                        "url": "https://unrelated.example/",
                        "title": "Nope",
                    }
                ]
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["renamed"], 0)
        self.assertEqual(self._link("Home").name, "Home")

    def test_changed_without_a_title_is_ignored(self) -> None:
        self._import([("Home", "https://home.example/")])

        status, payload = self.request(
            "POST",
            "/events",
            {"events": [{"type": "changed", "url": "https://home.example/"}]},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["renamed"], 0)
        self.assertEqual(self._link("Home").name, "Home")

    def test_events_are_processed_in_order(self) -> None:
        path = self._import(
            [
                ("Home", "https://home.example/"),
                ("Docs", "https://docs.example/"),
            ]
        )
        browser_before = path.read_bytes()

        status, payload = self.request(
            "POST",
            "/events",
            {
                "events": [
                    {
                        "type": "changed",
                        "url": "https://docs.example/",
                        "title": "Docs v2",
                    },
                    {"type": "removed", "url": "https://home.example/"},
                    # Unknown event types and malformed entries are skipped.
                    {"type": "added", "url": "https://home.example/"},
                    {"type": "removed"},
                ]
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True, "deleted": 1, "renamed": 1})
        names = [item.name for item in self.service.items("links")]
        self.assertIn("Docs v2", names)
        self.assertNotIn("Home", names)
        self.assertEqual(self.meta()["bookmarks"]["seenUrls"], ["https://docs.example"])
        self.assertEqual(path.read_bytes(), browser_before)

    def test_empty_event_batch_is_a_noop(self) -> None:
        self._import([("Home", "https://home.example/")])
        before = self.meta()

        status, payload = self.request("POST", "/events", {"events": []})

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True, "deleted": 0, "renamed": 0})
        self.assertEqual(self.meta(), before)
        self.assertEqual(self.writer_frames(), [])


if __name__ == "__main__":
    unittest.main()
