"""Protocol-level tests: framing, dispatch, error mapping, event channel."""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterator
from unittest import mock

from resource_hub_core.bookmark_bridge import BookmarkBridge
from resource_hub_core.bookmarks import BROWSER_DATA_DIRS_ENV
from resource_hub_core.browsers import Browser
from resource_hub_core.protocol import PROTOCOL_VERSION, JsonLinesServer


def http_json(
    port: int, method: str, path: str, payload: Any = None
) -> tuple[int, dict[str, Any]]:
    """One extension-style loopback request against a test bridge."""
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


class ProtocolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        # Never let a test read the developer's real Chrome/Edge bookmarks:
        # the server imports existing bookmarks on startup (Phase 17).
        self._browser_env = mock.patch.dict(
            os.environ, {BROWSER_DATA_DIRS_ENV: ""}
        )
        self._browser_env.start()

    def tearDown(self) -> None:
        self._browser_env.stop()
        self._tmp.cleanup()

    def run_frames(self, requests: list[dict[str, Any]], *, load: bool = True) -> list[dict[str, Any]]:
        payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests)
        out = io.StringIO()
        server = JsonLinesServer(
            self.dir,
            in_stream=io.StringIO(payload),
            out_stream=out,
            load=load,
        )
        server.serve_forever()
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def run_raw(self, raw: str, *, load: bool = True) -> list[dict[str, Any]]:
        out = io.StringIO()
        server = JsonLinesServer(
            self.dir, in_stream=io.StringIO(raw), out_stream=out, load=load
        )
        server.serve_forever()
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def call(self, method: str, params: dict[str, Any] | None = None, request_id: Any = 1) -> dict[str, Any]:
        frames = self.run_frames([{"id": request_id, "method": method, "params": params or {}}])
        self.assertEqual(len(frames), 1, frames)
        return frames[0]


class HelloTests(ProtocolTestCase):
    def test_hello_reports_protocol_and_methods(self) -> None:
        frame = self.call("app.hello")
        self.assertTrue(frame["ok"])
        result = frame["result"]
        self.assertEqual(result["protocolVersion"], PROTOCOL_VERSION)
        self.assertEqual(result["dataStatus"], "ok")
        self.assertIsNone(result["loadError"])
        self.assertIn("resources.list", result["methods"])
        self.assertIn("resources.reorder", result["methods"])
        self.assertIn("fs.children", result["methods"])
        self.assertIn("hotkey.start", result["methods"])
        self.assertIn("bookmarks.status", result["methods"])
        self.assertIn("bookmarks.sync", result["methods"])
        self.assertIn("favicons.map", result["methods"])
        self.assertIn("favicons.refresh", result["methods"])

    def test_hello_on_corrupt_data(self) -> None:
        (self.dir / "sites.json").write_text("[broken", encoding="utf-8")
        (self.dir / "folders.json").write_text("[]", encoding="utf-8")
        frame = self.call("app.hello")
        self.assertTrue(frame["ok"])
        self.assertEqual(frame["result"]["dataStatus"], "corrupt")
        self.assertIn("invalid JSON", frame["result"]["loadError"])


class FaviconTests(ProtocolTestCase):
    def test_map_reports_cached_icons(self) -> None:
        icons_dir = self.dir / "favicons"
        icons_dir.mkdir()
        (icons_dir / "abc.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (icons_dir / "index.json").write_text(
            json.dumps({"version": 1, "icons": {"example.com": "abc.png"}}),
            encoding="utf-8",
        )
        frame = self.call("favicons.map")
        self.assertTrue(frame["ok"])
        self.assertEqual(
            frame["result"]["icons"],
            {"example.com": str(icons_dir / "abc.png")},
        )

    def test_refresh_returns_the_cached_map_and_does_not_block(self) -> None:
        # The background fetch is not exercised here: it would open sockets.
        # `test_favicons.py` covers downloading against a local HTTP server.
        with mock.patch("resource_hub_core.protocol.Dispatcher._kick_favicons"):
            frames = self.run_frames(
                [{"id": 7, "method": "favicons.refresh", "params": {}}]
            )
        responses = [frame for frame in frames if frame.get("id") == 7]
        self.assertEqual(len(responses), 1, frames)
        self.assertTrue(responses[0]["ok"])
        self.assertEqual(responses[0]["result"], {"icons": {}})


class ResourceTests(ProtocolTestCase):
    def test_list_returns_sample_data_on_first_run(self) -> None:
        result = self.call("resources.list", {"mode": "links"})["result"]
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["visible"], 2)
        self.assertEqual(len(result["items"]), 2)
        self.assertIn("url", result["items"][0])

    def test_add_then_list(self) -> None:
        added = self.call(
            "resources.add",
            {"mode": "links", "name": "Docs", "target": "docs.example.com"},
        )
        self.assertTrue(added["ok"])
        self.assertEqual(added["result"]["item"]["url"], "https://docs.example.com")

        listed = self.call("resources.list", {"mode": "links"})["result"]
        self.assertEqual(listed["total"], 3)
        self.assertEqual(listed["items"][0]["name"], "Docs")

    def test_chinese_roundtrip(self) -> None:
        self.call(
            "resources.add",
            {"mode": "links", "name": "内部知识库", "target": "wiki.example.com", "note": "中文备注"},
        )
        result = self.call("resources.list", {"mode": "links"})["result"]
        self.assertEqual(result["items"][0]["name"], "内部知识库")
        self.assertEqual(result["items"][0]["note"], "中文备注")

    def test_list_filters_and_labels(self) -> None:
        self.call("resources.add", {"mode": "links", "name": "Alpha", "target": "https://a.test"})
        self.call("resources.add", {"mode": "links", "name": "Beta", "target": "https://b.test", "category": "工作"})

        by_query = self.call("resources.list", {"mode": "links", "query": "alph"})["result"]
        self.assertEqual([i["name"] for i in by_query["items"]], ["Alpha"])

        by_category = self.call("resources.list", {"mode": "links", "category": "工作"})["result"]
        self.assertEqual([i["name"] for i in by_category["items"]], ["Beta"])

        # Sentinels must be searchable through the injected localized label.
        by_label = self.call(
            "resources.list",
            {"mode": "links", "query": "未分类", "labels": {"uncategorized": "未分类"}},
        )["result"]
        names = {i["name"] for i in by_label["items"]}
        self.assertIn("Alpha", names)
        self.assertNotIn("Beta", names)

    def test_update_preserves_favorite(self) -> None:
        item_id = self.call(
            "resources.add", {"mode": "links", "name": "A", "target": "https://a.test"}
        )["result"]["item"]["id"]
        self.call("resources.favorite", {"mode": "links", "id": item_id, "value": True})

        updated = self.call(
            "resources.update",
            {"mode": "links", "id": item_id, "name": "A2", "target": "https://a2.test"},
        )["result"]["item"]
        self.assertEqual(updated["name"], "A2")
        self.assertTrue(updated["favorite"])

    def test_favorite_toggles_without_value(self) -> None:
        item_id = self.call(
            "resources.add", {"mode": "links", "name": "A", "target": "https://a.test"}
        )["result"]["item"]["id"]
        first = self.call("resources.favorite", {"mode": "links", "id": item_id})["result"]["item"]
        self.assertTrue(first["favorite"])
        second = self.call("resources.favorite", {"mode": "links", "id": item_id})["result"]["item"]
        self.assertFalse(second["favorite"])

    def test_delete(self) -> None:
        item_id = self.call(
            "resources.add", {"mode": "links", "name": "A", "target": "https://a.test"}
        )["result"]["item"]["id"]
        self.assertTrue(self.call("resources.delete", {"mode": "links", "id": item_id})["result"]["deleted"])
        self.assertFalse(self.call("resources.delete", {"mode": "links", "id": item_id})["result"]["deleted"])

    def test_reorder_roundtrip(self) -> None:
        listed = self.call("resources.list", {"mode": "links"})["result"]["items"]
        ids = [item["id"] for item in listed]
        reversed_ids = list(reversed(ids))

        frame = self.call("resources.reorder", {"mode": "links", "ids": reversed_ids})
        self.assertTrue(frame["ok"], frame)
        self.assertEqual(
            [item["id"] for item in frame["result"]["items"]], reversed_ids
        )
        after = self.call("resources.list", {"mode": "links"})["result"]["items"]
        self.assertEqual([item["id"] for item in after], reversed_ids)

    def test_reorder_rejects_a_partial_id_list(self) -> None:
        listed = self.call("resources.list", {"mode": "links"})["result"]["items"]
        frame = self.call(
            "resources.reorder",
            {"mode": "links", "ids": [listed[0]["id"]]},
        )
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "operation_failed")
        self.assertEqual(frame["error"]["key"], "reorder_failed")

    def test_reorder_requires_an_id_array(self) -> None:
        frame = self.call("resources.reorder", {"mode": "links", "ids": "nope"})
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "bad_request")

    def test_check_paths(self) -> None:
        result = self.call("resources.checkPaths", {"mode": "links"})["result"]
        self.assertFalse(result["supported"])

        target = self.dir / "gone"
        target.mkdir()
        self.call("resources.add", {"mode": "folders", "name": "Gone", "target": str(target)})
        target.rmdir()
        result = self.call("resources.checkPaths", {"mode": "folders"})["result"]
        self.assertTrue(result["supported"])
        self.assertEqual(result["missingCount"], 1)

    def test_export_and_import(self) -> None:
        exported = self.call("resources.export", {"mode": "links"})["result"]["items"]
        self.assertEqual(len(exported), 2)

        result = self.call("resources.import", {"mode": "links", "items": exported[:1]})["result"]
        self.assertEqual(result["imported"], 1)

        listed = self.call("resources.list", {"mode": "links"})["result"]
        self.assertEqual(listed["total"], 1)

    def test_drop(self) -> None:
        target = self.dir / "dropped"
        target.mkdir()
        result = self.call(
            "resources.drop", {"paths": [str(target), str(self.dir / "missing")]}
        )["result"]
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["invalid"], 1)

    def test_open_link_delegates_to_launcher(self) -> None:
        item_id = self.call(
            "resources.add", {"mode": "links", "name": "A", "target": "https://a.test"}
        )["result"]["item"]["id"]
        with mock.patch("resource_hub_core.protocol.open_link") as opener:
            frame = self.call("resources.open", {"mode": "links", "id": item_id})
        self.assertTrue(frame["ok"])
        opener.assert_called_once_with("https://a.test", None)

    def test_open_link_uses_the_site_browser(self) -> None:
        item_id = self.call(
            "resources.add",
            {
                "mode": "links",
                "name": "A",
                "target": "https://a.test",
                "browser": "chrome",
            },
        )["result"]["item"]["id"]
        fake = Browser("chrome", "Google Chrome", r"C:\chrome.exe")
        with (
            mock.patch("resource_hub_core.protocol.open_link") as opener,
            mock.patch(
                "resource_hub_core.protocol.find_browser", return_value=fake
            ) as finder,
        ):
            frame = self.call("resources.open", {"mode": "links", "id": item_id})
        self.assertTrue(frame["ok"])
        finder.assert_called_once_with("chrome")
        opener.assert_called_once_with("https://a.test", fake)

    def test_open_link_browser_override_wins(self) -> None:
        item_id = self.call(
            "resources.add",
            {
                "mode": "links",
                "name": "A",
                "target": "https://a.test",
                "browser": "chrome",
            },
        )["result"]["item"]["id"]
        fake = Browser("edge", "Microsoft Edge", r"C:\msedge.exe")
        with (
            mock.patch("resource_hub_core.protocol.open_link") as opener,
            mock.patch(
                "resource_hub_core.protocol.find_browser", return_value=fake
            ) as finder,
        ):
            self.call(
                "resources.open",
                {"mode": "links", "id": item_id, "browser": "edge"},
            )
        finder.assert_called_once_with("edge")
        opener.assert_called_once_with("https://a.test", fake)

    def test_update_sets_the_site_browser(self) -> None:
        item_id = self.call(
            "resources.add", {"mode": "links", "name": "A", "target": "https://a.test"}
        )["result"]["item"]["id"]
        updated = self.call(
            "resources.update",
            {
                "mode": "links",
                "id": item_id,
                "name": "A",
                "target": "https://a.test",
                "browser": "edge",
            },
        )["result"]["item"]
        self.assertEqual(updated["browser"], "edge")
        # Omitting the key keeps the stored choice.
        kept = self.call(
            "resources.update",
            {"mode": "links", "id": item_id, "name": "A2", "target": "https://a.test"},
        )["result"]["item"]
        self.assertEqual(kept["browser"], "edge")

    def test_browsers_list_returns_installed_browsers(self) -> None:
        fake = [Browser("chrome", "Google Chrome", r"C:\chrome.exe")]
        with mock.patch(
            "resource_hub_core.protocol.installed_browsers", return_value=fake
        ):
            result = self.call("browsers.list")["result"]
        self.assertEqual(
            result["browsers"],
            [{"id": "chrome", "name": "Google Chrome", "path": r"C:\chrome.exe"}],
        )

    def test_open_missing_folder_reports_operation_failure(self) -> None:
        target = self.dir / "gone-soon"
        target.mkdir()
        item_id = self.call(
            "resources.add", {"mode": "folders", "name": "Gone", "target": str(target)}
        )["result"]["item"]["id"]
        target.rmdir()

        frame = self.call("resources.open", {"mode": "folders", "id": item_id})
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "operation_failed")
        self.assertEqual(frame["error"]["key"], "open_folder_failed")

    def test_reveal_delegates_to_launcher(self) -> None:
        target = self.dir / "reveal-me"
        target.mkdir()
        item_id = self.call(
            "resources.add", {"mode": "folders", "name": "R", "target": str(target)}
        )["result"]["item"]["id"]
        with mock.patch("resource_hub_core.protocol.reveal_path") as revealer:
            frame = self.call("resources.reveal", {"mode": "folders", "id": item_id})
        self.assertTrue(frame["ok"])
        revealer.assert_called_once_with(str(target))


class FsTests(ProtocolTestCase):
    def test_children_lists_folders_first(self) -> None:
        root = self.dir / "listing"
        root.mkdir()
        (root / "beta").mkdir()
        (root / "Alpha").mkdir()
        (root / "note.txt").write_text("x", encoding="utf-8")

        result = self.call("fs.children", {"path": str(root)})["result"]

        self.assertEqual(
            [entry["name"] for entry in result["entries"]],
            ["Alpha", "beta", "note.txt"],
        )
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["shown"], 3)
        self.assertFalse(result["truncated"])

    def test_children_missing_path_reports_operation_failure(self) -> None:
        frame = self.call("fs.children", {"path": str(self.dir / "nope")})
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "operation_failed")
        self.assertEqual(frame["error"]["key"], "fs_not_found")

    def test_children_requires_a_path(self) -> None:
        frame = self.call("fs.children", {})
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "bad_request")

    def test_open_delegates_to_launcher(self) -> None:
        target = self.dir / "open-me"
        target.mkdir()
        with mock.patch("resource_hub_core.fs.open_path") as opener:
            frame = self.call("fs.open", {"path": str(target)})
        self.assertTrue(frame["ok"])
        opener.assert_called_once_with(str(target))

    def test_reveal_delegates_to_launcher(self) -> None:
        target = self.dir / "reveal-me"
        target.mkdir()
        with mock.patch("resource_hub_core.fs.reveal_path") as revealer:
            frame = self.call("fs.reveal", {"path": str(target)})
        self.assertTrue(frame["ok"])
        revealer.assert_called_once_with(str(target))


class SettingsTests(ProtocolTestCase):
    def test_get_returns_defaults(self) -> None:
        settings = self.call("settings.get")["result"]["settings"]
        self.assertEqual(settings["language"], "zh")
        self.assertEqual(settings["globalHotkeyId"], "Ctrl + Alt + Space")
        self.assertEqual(settings["quickLinksHotkeyId"], "Ctrl + Alt + Shift + L")
        self.assertEqual(settings["quickFoldersHotkeyId"], "Ctrl + Alt + Shift + F")

    def test_set_normalises_and_persists(self) -> None:
        result = self.call(
            "settings.set",
            {
                "settings": {
                    "language": "en",
                    "globalHotkeyId": "control+shift+q",
                    "quickLinksHotkeyId": "control+shift+l",
                    "quickFoldersHotkeyId": "alt+control+f",
                }
            },
        )["result"]["settings"]
        self.assertEqual(result["language"], "en")
        self.assertEqual(result["globalHotkeyId"], "Ctrl + Shift + Q")
        self.assertEqual(result["quickLinksHotkeyId"], "Ctrl + Shift + L")
        self.assertEqual(result["quickFoldersHotkeyId"], "Ctrl + Alt + F")

        persisted = json.loads((self.dir / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["language"], "en")
        self.assertEqual(persisted["quickLinksHotkeyId"], "Ctrl + Shift + L")
        self.assertEqual(persisted["quickFoldersHotkeyId"], "Ctrl + Alt + F")

    def test_set_rejects_non_object(self) -> None:
        frame = self.call("settings.set", {"settings": "nope"})
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "bad_request")

    def test_probe_hotkey_rejects_invalid(self) -> None:
        self.assertFalse(self.call("settings.probeHotkey", {"hotkeyId": "Nope"})["result"]["available"])

    def test_get_includes_bookmark_defaults(self) -> None:
        settings = self.call("settings.get")["result"]["settings"]
        self.assertIs(settings["bookmarkSyncEnabled"], True)
        self.assertEqual(settings["bookmarkCustomDir"], "")
        self.assertEqual(settings["bookmarkDeleteMode"], "ask")

    def test_set_normalises_bookmark_settings(self) -> None:
        result = self.call(
            "settings.set",
            {
                "settings": {
                    "bookmarkSyncEnabled": False,
                    "bookmarkCustomDir": "  D:\\Bookmarks  ",
                    "bookmarkDeleteMode": "keep",
                }
            },
        )["result"]["settings"]
        self.assertIs(result["bookmarkSyncEnabled"], False)
        self.assertEqual(result["bookmarkCustomDir"], "D:\\Bookmarks")
        self.assertEqual(result["bookmarkDeleteMode"], "keep")

        persisted = json.loads((self.dir / "settings.json").read_text(encoding="utf-8"))
        self.assertIs(persisted["bookmarkSyncEnabled"], False)
        self.assertEqual(persisted["bookmarkCustomDir"], "D:\\Bookmarks")
        self.assertEqual(persisted["bookmarkDeleteMode"], "keep")

    def test_set_normalises_an_invalid_bookmark_delete_mode(self) -> None:
        result = self.call(
            "settings.set", {"settings": {"bookmarkDeleteMode": "delete-everything"}}
        )["result"]["settings"]
        self.assertEqual(result["bookmarkDeleteMode"], "ask")


class BookmarkBridgeTests(ProtocolTestCase):
    """Protocol surface of the browser bookmark bridge (Phase 17).

    ``RH_BROWSER_DATA_DIRS`` is pinned so these tests never read the real
    Chrome/Edge data of the machine running them.
    """

    def setUp(self) -> None:
        super().setUp()
        self._env = mock.patch.dict(os.environ, {BROWSER_DATA_DIRS_ENV: ""})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        super().tearDown()

    @staticmethod
    def _write_bookmarks(root: Path, payload: dict[str, Any]) -> None:
        profile = root / "Default"
        profile.mkdir(parents=True)
        (profile / "Bookmarks").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def test_status_on_an_empty_data_dir(self) -> None:
        result = self.call("bookmarks.status")["result"]

        self.assertEqual(
            result,
            {
                "enabled": True,
                "customDir": "",
                "profiles": [],
                "lastSyncAt": None,
                "syncedUrls": 0,
            },
        )

    def test_sync_imports_bookmarks_and_emits_event(self) -> None:
        root = self.dir / "Chrome"
        self._write_bookmarks(
            root,
            {
                "roots": {
                    "bookmark_bar": {
                        "type": "folder",
                        "name": "Bookmarks bar",
                        "children": [
                            {"type": "url", "name": "Home", "url": "https://home.example/"},
                            {
                                "type": "folder",
                                "name": "开发",
                                "children": [
                                    {
                                        "type": "url",
                                        "name": "Python",
                                        "url": "https://python.org/",
                                    }
                                ],
                            },
                        ],
                    }
                }
            },
        )
        os.environ[BROWSER_DATA_DIRS_ENV] = str(root)

        frames = self.run_frames(
            [{"id": 1, "method": "bookmarks.sync", "params": {}}]
        )

        # The server imports existing bookmarks before serving the first
        # request, so the explicit sync is already a no-op…
        response = next(frame for frame in frames if frame.get("id") == 1)
        self.assertTrue(response["ok"], response)
        result = response["result"]
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["skipped"], 2)
        self.assertEqual(result["total"], 2)
        self.assertIsInstance(result["lastSyncAt"], str)
        self.assertEqual(
            result["profiles"],
            [
                {
                    "label": "Chrome · Default",
                    "path": str(root / "Default" / "Bookmarks"),
                    "bookmarks": 2,
                }
            ],
        )

        # …while the startup import itself announced the additions.
        events = [frame for frame in frames if frame.get("event") == "bookmarks"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["added"], 2)
        self.assertEqual(
            events[0]["payload"]["profiles"], result["profiles"]
        )

        stored = json.loads((self.dir / "sites.json").read_text(encoding="utf-8"))
        by_name = {entry["name"]: entry for entry in stored}
        self.assertEqual(len(stored), 4)  # two first-run samples + two imports
        self.assertEqual(by_name["Home"]["category"], "书签栏")
        self.assertEqual(by_name["Python"]["category"], "开发")

    def test_sync_is_idempotent_through_the_protocol(self) -> None:
        root = self.dir / "Chrome"
        self._write_bookmarks(
            root,
            {
                "roots": {
                    "bookmark_bar": {
                        "type": "folder",
                        "name": "bar",
                        "children": [
                            {"type": "url", "name": "A", "url": "https://a.example/"}
                        ],
                    }
                }
            },
        )
        os.environ[BROWSER_DATA_DIRS_ENV] = str(root)

        frames = self.run_frames(
            [
                {"id": 1, "method": "bookmarks.sync", "params": {}},
                {"id": 2, "method": "bookmarks.sync", "params": {}},
            ]
        )

        results = [
            frame["result"] for frame in frames if frame.get("id") in (1, 2)
        ]
        self.assertEqual([result["added"] for result in results], [0, 0])
        # Only the startup import is announced; no-op syncs stay silent.
        events = [frame for frame in frames if frame.get("event") == "bookmarks"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["added"], 1)

    def test_custom_dir_set_through_settings_is_used_by_sync(self) -> None:
        profile = self.dir / "custom-browser" / "Default"
        profile.mkdir(parents=True)
        (profile / "Bookmarks").write_text(
            json.dumps(
                {
                    "roots": {
                        "bookmark_bar": {
                            "type": "folder",
                            "name": "bar",
                            "children": [
                                {
                                    "type": "url",
                                    "name": "Custom",
                                    "url": "https://custom.example/",
                                }
                            ],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        frames = self.run_frames(
            [
                {
                    "id": 1,
                    "method": "settings.set",
                    "params": {"settings": {"bookmarkCustomDir": str(profile)}},
                },
                {"id": 2, "method": "bookmarks.sync", "params": {}},
                {"id": 3, "method": "bookmarks.status", "params": {}},
            ]
        )

        by_id = {frame["id"]: frame for frame in frames if "id" in frame}
        sync_result = by_id[2]["result"]
        self.assertEqual(sync_result["added"], 1)
        self.assertEqual(sync_result["profiles"][0]["label"], "自定义")
        status = by_id[3]["result"]
        self.assertEqual(status["customDir"], str(profile))
        self.assertEqual(status["syncedUrls"], 1)
        stored = json.loads((self.dir / "sites.json").read_text(encoding="utf-8"))
        self.assertIn("Custom", [entry["name"] for entry in stored])

    def test_sync_with_corrupt_data_file_fails_cleanly(self) -> None:
        (self.dir / "sites.json").write_text("[broken", encoding="utf-8")
        (self.dir / "folders.json").write_text("[]", encoding="utf-8")

        frame = self.call("bookmarks.sync")

        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "corrupt_data")
        self.assertEqual(frame["error"]["key"], "data_corrupt")

    def test_serve_forever_starts_and_stops_the_watcher(self) -> None:
        out = io.StringIO()
        server = JsonLinesServer(
            self.dir, in_stream=io.StringIO(""), out_stream=out
        )
        with (
            mock.patch(
                "resource_hub_core.protocol.BookmarkWatcher.start"
            ) as start,
            mock.patch("resource_hub_core.protocol.BookmarkWatcher.stop") as stop,
        ):
            server.serve_forever()

        start.assert_called_once()
        stop.assert_called_once()
        self.assertIsNone(server.state.bookmark_watcher)

    def test_watcher_is_not_started_on_corrupt_data(self) -> None:
        (self.dir / "sites.json").write_text("[broken", encoding="utf-8")
        (self.dir / "folders.json").write_text("[]", encoding="utf-8")
        out = io.StringIO()
        server = JsonLinesServer(
            self.dir, in_stream=io.StringIO(""), out_stream=out
        )
        with mock.patch("resource_hub_core.protocol.BookmarkWatcher.start") as start:
            server.serve_forever()

        start.assert_not_called()


class ExtensionBridgeProtocolTests(ProtocolTestCase):
    """Phase 18: extension status, bookmark matches and the browser removal queue."""

    @contextlib.contextmanager
    def _running_server(self) -> Iterator[JsonLinesServer]:
        """A server with the bookmark startup pass and the loopback bridge up."""
        server = JsonLinesServer(
            self.dir, in_stream=io.StringIO(""), out_stream=io.StringIO()
        )
        server._start_bookmarks()
        server._start_bridge()
        try:
            yield server
        finally:
            server._shutdown()

    def test_hello_lists_the_extension_methods(self) -> None:
        methods = self.call("app.hello")["result"]["methods"]
        self.assertIn("bookmarks.extensionStatus", methods)
        self.assertIn("bookmarks.matches", methods)
        # The list stays sorted (the UI diffs it when it refreshes).
        self.assertEqual(methods, sorted(methods))

    def test_extension_status_on_a_fresh_server(self) -> None:
        with self._running_server() as server:
            status = server.dispatcher.dispatch("bookmarks.extensionStatus", {})

        self.assertFalse(status["connected"])
        self.assertIsNone(status["lastSeenAt"])
        self.assertIsInstance(status["port"], int)
        self.assertEqual(status["pendingCommands"], 0)
        self.assertEqual(
            status["extensionPath"], str(self.dir / "bookmark-extension")
        )

    def test_extension_status_is_disconnected_without_a_bridge(self) -> None:
        out = io.StringIO()
        server = JsonLinesServer(self.dir, in_stream=io.StringIO(""), out_stream=out)
        result = server.dispatcher.dispatch("bookmarks.extensionStatus", {})
        self.assertFalse(result["connected"])
        self.assertIsNone(result["port"])
        self.assertEqual(result["pendingCommands"], 0)

    def test_ping_marks_the_extension_connected(self) -> None:
        with self._running_server() as server:
            bridge = server.state.bookmark_bridge
            self.assertIsInstance(bridge, BookmarkBridge)
            assert bridge is not None

            status, payload = http_json(bridge.port or 0, "GET", "/ping")
            self.assertEqual(status, 200)
            self.assertEqual(payload, {"app": "resource-hub", "protocol": 1})

            result = server.dispatcher.dispatch("bookmarks.extensionStatus", {})
            self.assertTrue(result["connected"])
            self.assertEqual(result["lastSeenAt"], bridge.last_seen_iso)
            self.assertEqual(result["port"], bridge.port)

    def test_delete_link_with_remove_from_browser_queues_a_command(self) -> None:
        with self._running_server() as server:
            added = server.dispatcher.dispatch(
                "resources.add",
                {"mode": "links", "name": "Gone", "target": "https://gone.example/x"},
            )["item"]

            result = server.dispatcher.dispatch(
                "resources.delete",
                {"mode": "links", "id": added["id"], "removeFromBrowser": True},
            )

            self.assertTrue(result["deleted"])
            self.assertTrue(result["browserQueued"])
            self.assertFalse(result["extensionConnected"])

            status = server.dispatcher.dispatch("bookmarks.extensionStatus", {})
            self.assertEqual(status["pendingCommands"], 1)

            # Act like the extension: poll, then acknowledge.
            code, payload = http_json(bridge_port(server), "GET", "/commands")
            self.assertEqual(code, 200)
            commands = payload["commands"]
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0]["op"], "remove")
            self.assertEqual(commands[0]["urls"], ["https://gone.example/x"])
            self.assertIsInstance(commands[0]["createdAt"], str)

            code, ack = http_json(
                bridge_port(server),
                "POST",
                "/ack",
                {"results": [{"id": commands[0]["id"], "removed": 1, "failed": 0}]},
            )
            self.assertEqual(code, 200)
            self.assertEqual(ack, {"ok": True})

            status = server.dispatcher.dispatch("bookmarks.extensionStatus", {})
            self.assertEqual(status["pendingCommands"], 0)
            # Polling marked the extension alive, so the next delete can report it.
            self.assertTrue(status["connected"])

    def test_delete_without_remove_from_browser_queues_nothing(self) -> None:
        with self._running_server() as server:
            added = server.dispatcher.dispatch(
                "resources.add",
                {"mode": "links", "name": "Local", "target": "https://local.example/"},
            )["item"]

            result = server.dispatcher.dispatch(
                "resources.delete", {"mode": "links", "id": added["id"]}
            )

            self.assertTrue(result["deleted"])
            self.assertFalse(result["browserQueued"])
            self.assertFalse(result["extensionConnected"])
            self.assertEqual(
                server.dispatcher.dispatch(
                    "bookmarks.extensionStatus", {}
                )["pendingCommands"],
                0,
            )

    def test_delete_folder_never_queues_a_browser_command(self) -> None:
        target = self.dir / "some-folder"
        target.mkdir()
        with self._running_server() as server:
            added = server.dispatcher.dispatch(
                "resources.add",
                {"mode": "folders", "name": "F", "target": str(target)},
            )["item"]

            result = server.dispatcher.dispatch(
                "resources.delete",
                {"mode": "folders", "id": added["id"], "removeFromBrowser": True},
            )

            self.assertTrue(result["deleted"])
            self.assertFalse(result["browserQueued"])
            self.assertFalse(result["extensionConnected"])
            bridge = server.state.bookmark_bridge
            assert bridge is not None
            self.assertEqual(bridge.pending_count(), 0)

    def test_delete_unknown_link_with_remove_from_browser_is_a_noop(self) -> None:
        with self._running_server() as server:
            result = server.dispatcher.dispatch(
                "resources.delete",
                {"mode": "links", "id": "missing", "removeFromBrowser": True},
            )
            self.assertFalse(result["deleted"])
            self.assertFalse(result["browserQueued"])
            bridge = server.state.bookmark_bridge
            assert bridge is not None
            self.assertEqual(bridge.pending_count(), 0)

    def test_delete_without_a_running_bridge_keeps_flags_false(self) -> None:
        server = JsonLinesServer(
            self.dir, in_stream=io.StringIO(""), out_stream=io.StringIO()
        )
        server._start_bookmarks()
        try:
            added = server.dispatcher.dispatch(
                "resources.add",
                {"mode": "links", "name": "NoBridge", "target": "https://x.example/"},
            )["item"]
            result = server.dispatcher.dispatch(
                "resources.delete",
                {"mode": "links", "id": added["id"], "removeFromBrowser": True},
            )
        finally:
            server._shutdown()

        self.assertTrue(result["deleted"])
        self.assertFalse(result["browserQueued"])
        self.assertFalse(result["extensionConnected"])
        self.assertIsNone(server.state.bookmark_bridge)

    def test_bookmarks_matches_reads_the_browser_profiles(self) -> None:
        root = self.dir / "Chrome"
        profile = root / "Default"
        profile.mkdir(parents=True)
        (profile / "Bookmarks").write_text(
            json.dumps(
                {
                    "roots": {
                        "bookmark_bar": {
                            "type": "folder",
                            "name": "bar",
                            "children": [
                                {"type": "url", "name": "Home", "url": "https://home.example/"},
                                {
                                    "type": "folder",
                                    "name": "开发",
                                    "children": [
                                        {
                                            "type": "url",
                                            "name": "PyPI",
                                            "url": "https://pypi.org/",
                                        }
                                    ],
                                },
                            ],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        os.environ[BROWSER_DATA_DIRS_ENV] = str(root)

        result = next(
            frame
            for frame in self.run_frames(
                [
                    {
                        "id": 1,
                        "method": "bookmarks.matches",
                        "params": {
                            "urls": ["https://HOME.example", "https://nope.example/"]
                        },
                    }
                ]
            )
            if frame.get("id") == 1
        )["result"]

        self.assertEqual(len(result["matches"]), 1)
        match = result["matches"][0]
        self.assertEqual(match["url"], "https://home.example/")
        self.assertEqual(match["title"], "Home")
        self.assertEqual(match["label"], "Chrome · Default")
        self.assertEqual(match["path"], "书签栏")

    def test_bookmarks_matches_returns_empty_for_no_input_or_profiles(self) -> None:
        self.assertEqual(self.call("bookmarks.matches", {"urls": []})["result"],
                         {"matches": []})
        self.assertEqual(self.call("bookmarks.matches", {})["result"],
                         {"matches": []})
        self.assertEqual(
            self.call("bookmarks.matches", {"urls": ["https://a.example/"]})["result"],
            {"matches": []},
        )

    def test_bookmarks_matches_rejects_a_non_string_list(self) -> None:
        frame = self.call("bookmarks.matches", {"urls": "https://a.example/"})
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "bad_request")

    def test_serve_forever_starts_and_stops_the_bridge(self) -> None:
        server = JsonLinesServer(
            self.dir, in_stream=io.StringIO(""), out_stream=io.StringIO()
        )
        ports: list[int] = []
        original_start = server._start_bridge

        def spy_start() -> None:
            original_start()
            bridge = server.state.bookmark_bridge
            if bridge is not None and bridge.port is not None:
                ports.append(bridge.port)

        server._start_bridge = spy_start  # type: ignore[method-assign]
        server.serve_forever()

        # The finally-path stopped it and released the port.
        self.assertIsNone(server.state.bookmark_bridge)
        self.assertEqual(len(ports), 1)
        with self.assertRaises(OSError):
            http_json(ports[0], "GET", "/ping")

    def test_bridge_is_not_started_on_corrupt_data(self) -> None:
        (self.dir / "sites.json").write_text("[broken", encoding="utf-8")
        (self.dir / "folders.json").write_text("[]", encoding="utf-8")
        server = JsonLinesServer(
            self.dir, in_stream=io.StringIO(""), out_stream=io.StringIO()
        )
        server.serve_forever()
        self.assertIsNone(server.state.bookmark_bridge)


def bridge_port(server: JsonLinesServer) -> int:
    """The running bridge's port as an int (fails the test when absent)."""
    bridge = server.state.bookmark_bridge
    if bridge is None or bridge.port is None:
        raise AssertionError("bookmark bridge is not running")
    return bridge.port


class ErrorMappingTests(ProtocolTestCase):
    def test_validation_error_carries_i18n_key(self) -> None:
        frame = self.call("resources.add", {"mode": "links", "name": "", "target": "https://a.test"})
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "validation")
        self.assertEqual(frame["error"]["key"], "enter_link_name")

    def test_duplicate_error(self) -> None:
        frame = self.call("resources.add", {"mode": "links", "name": "GH", "target": "https://github.com/"})
        self.assertEqual(frame["error"]["code"], "duplicate")
        self.assertEqual(frame["error"]["key"], "duplicate_link_path")

    def test_not_found(self) -> None:
        frame = self.call("resources.favorite", {"mode": "links", "id": "does-not-exist"})
        self.assertEqual(frame["error"]["code"], "not_found")
        self.assertEqual(frame["error"]["key"], "select_first_link")

    def test_unknown_method(self) -> None:
        frame = self.call("resources.nope")
        self.assertEqual(frame["error"]["code"], "unknown_method")

    def test_invalid_mode(self) -> None:
        frame = self.call("resources.list", {"mode": "bookmarks"})
        self.assertEqual(frame["error"]["code"], "bad_request")

    def test_missing_string_param(self) -> None:
        frame = self.call("resources.add", {"mode": "links", "name": "A"})
        self.assertEqual(frame["error"]["code"], "bad_request")

    def test_corrupt_data_refuses_mutations(self) -> None:
        (self.dir / "sites.json").write_text("[broken", encoding="utf-8")
        (self.dir / "folders.json").write_text("[]", encoding="utf-8")
        frames = self.run_frames(
            [
                {"id": 1, "method": "resources.list", "params": {"mode": "links"}},
                {
                    "id": 2,
                    "method": "resources.add",
                    "params": {"mode": "links", "name": "A", "target": "https://a.test"},
                },
            ]
        )
        for frame in frames:
            self.assertFalse(frame["ok"])
            self.assertEqual(frame["error"]["code"], "corrupt_data")
            self.assertEqual(frame["error"]["key"], "data_corrupt")
        # The unreadable file must be left exactly as it was.
        self.assertEqual(
            (self.dir / "sites.json").read_text(encoding="utf-8"), "[broken"
        )


class FramingTests(ProtocolTestCase):
    def test_id_is_echoed_including_strings(self) -> None:
        frames = self.run_frames(
            [
                {"id": "req-a", "method": "app.hello", "params": {}},
                {"id": 42, "method": "app.hello", "params": {}},
            ]
        )
        self.assertEqual([f["id"] for f in frames], ["req-a", 42])

    def test_malformed_json_yields_error_with_null_id(self) -> None:
        frames = self.run_raw("{not json}\n")
        self.assertEqual(len(frames), 1)
        self.assertIsNone(frames[0]["id"])
        self.assertEqual(frames[0]["error"]["code"], "bad_request")

    def test_missing_method(self) -> None:
        frames = self.run_frames([{"id": 7, "params": {}}])
        self.assertEqual(frames[0]["error"]["code"], "bad_request")
        self.assertEqual(frames[0]["id"], 7)

    def test_blank_lines_are_ignored(self) -> None:
        frames = self.run_raw('\n\n{"id":1,"method":"app.hello","params":{}}\n\n')
        self.assertEqual(len(frames), 1)

    def test_each_frame_is_one_line(self) -> None:
        out = io.StringIO()
        server = JsonLinesServer(
            self.dir,
            in_stream=io.StringIO('{"id":1,"method":"resources.list","params":{"mode":"folders"}}\n'),
            out_stream=out,
        )
        server.serve_forever()
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertNotIn("\n", lines[0])

    def test_shutdown_stops_the_loop(self) -> None:
        frames = self.run_frames(
            [
                {"id": 1, "method": "app.shutdown", "params": {}},
                {"id": 2, "method": "app.hello", "params": {}},
            ]
        )
        self.assertEqual(len(frames), 1)
        self.assertTrue(frames[0]["result"]["shutdown"])


class EventChannelTests(ProtocolTestCase):
    def test_event_frame_shape(self) -> None:
        out = io.StringIO()
        server = JsonLinesServer(self.dir, in_stream=io.StringIO(""), out_stream=out)
        server.writer.event("hotkey", {"action": "toggle"})
        frame = json.loads(out.getvalue().strip())
        self.assertNotIn("id", frame)
        self.assertEqual(frame["event"], "hotkey")
        self.assertEqual(frame["payload"]["action"], "toggle")

    def test_hotkey_start_reports_disabled_when_switched_off(self) -> None:
        self.call("settings.set", {"settings": {"globalHotkeyEnabled": False}})
        result = self.call("hotkey.start")["result"]
        self.assertFalse(result["registered"])
        self.assertEqual(result["label"], "Ctrl + Alt + Space")
        self.assertEqual(result["reason"], "disabled")
        self.assertEqual(
            result["registrations"],
            [
                {
                    "action": "toggle",
                    "label": "Ctrl + Alt + Space",
                    "registered": False,
                    "reason": "disabled",
                },
                {
                    "action": "quickLinks",
                    "label": "Ctrl + Alt + Shift + L",
                    "registered": False,
                    "reason": "disabled",
                },
                {
                    "action": "quickFolders",
                    "label": "Ctrl + Alt + Shift + F",
                    "registered": False,
                    "reason": "disabled",
                },
            ],
        )

    def test_hotkey_start_disabled_uses_configured_quick_labels(self) -> None:
        self.call(
            "settings.set",
            {
                "settings": {
                    "globalHotkeyEnabled": False,
                    "quickLinksHotkeyId": "control+shift+l",
                    "quickFoldersHotkeyId": "control+shift+f",
                }
            },
        )
        result = self.call("hotkey.start")["result"]
        self.assertEqual(
            [entry["label"] for entry in result["registrations"]],
            ["Ctrl + Alt + Space", "Ctrl + Shift + L", "Ctrl + Shift + F"],
        )


    def test_hotkey_start_reports_disabled_mouse_buttons(self) -> None:
        self.call("settings.set", {"settings": {"globalHotkeyEnabled": False}})
        mouse = self.call("hotkey.start")["result"]["mouseSideButtons"]
        self.assertEqual(
            mouse,
            {"enabled": False, "registered": False, "reason": "disabled"},
        )

    def test_mouse_side_buttons_start_independently_of_hotkeys(self) -> None:
        started: list[Any] = []

        class FakeMouse:
            def __init__(self, on_action: Any) -> None:
                self.on_action = on_action
                self.stopped = False

            def start(self, timeout: float = 2.0) -> bool:
                started.append(self)
                return True

            def stop(self, timeout: float = 2.0) -> None:
                self.stopped = True

        self.call(
            "settings.set",
            {
                "settings": {
                    "globalHotkeyEnabled": False,
                    "mouseSideButtonsEnabled": True,
                }
            },
        )
        with mock.patch(
            "resource_hub_core.protocol.MouseSideButtonListener", FakeMouse
        ):
            result = self.call("hotkey.start")["result"]
        self.assertTrue(result["mouseSideButtons"]["enabled"])
        self.assertTrue(result["mouseSideButtons"]["registered"])
        self.assertIsNone(result["mouseSideButtons"]["reason"])
        self.assertEqual(len(started), 1)
        self.call("hotkey.stop")
        self.assertTrue(started[0].stopped)


if __name__ == "__main__":
    unittest.main()
