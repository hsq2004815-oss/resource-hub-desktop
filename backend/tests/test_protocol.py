"""Protocol-level tests: framing, dispatch, error mapping, event channel."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from resource_hub_core.protocol import PROTOCOL_VERSION, JsonLinesServer


class ProtocolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
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

    def test_hello_on_corrupt_data(self) -> None:
        (self.dir / "sites.json").write_text("[broken", encoding="utf-8")
        (self.dir / "folders.json").write_text("[]", encoding="utf-8")
        frame = self.call("app.hello")
        self.assertTrue(frame["ok"])
        self.assertEqual(frame["result"]["dataStatus"], "corrupt")
        self.assertIn("invalid JSON", frame["result"]["loadError"])


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
        opener.assert_called_once_with("https://a.test")

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


if __name__ == "__main__":
    unittest.main()
