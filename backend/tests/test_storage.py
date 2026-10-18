"""Tests for atomic persistence and the ADR-001 D3 guarantees."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from resource_hub_core.storage import CorruptDataError, JsonFileStore, atomic_write_text


class LoadTests(unittest.TestCase):
    def test_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonFileStore(Path(tmp) / "sites.json")
            with self.assertRaises(FileNotFoundError):
                store.load()
            self.assertIsNone(store.load_or_none())

    def test_valid_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sites.json"
            path.write_text('[{"name": "a"}]', encoding="utf-8")
            self.assertEqual(JsonFileStore(path).load(), [{"name": "a"}])

    def test_corrupt_json_raises_and_preserves_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sites.json"
            broken = '[{"name": "a", '  # truncated write
            path.write_text(broken, encoding="utf-8")

            with self.assertRaises(CorruptDataError) as ctx:
                JsonFileStore(path).load()
            self.assertIn("invalid JSON", ctx.exception.detail)
            # The whole point of D3: never touch a file we failed to understand.
            self.assertEqual(path.read_text(encoding="utf-8"), broken)

    def test_empty_file_is_treated_as_corrupt(self) -> None:
        # An empty file is what a crashed write leaves behind; treating it as
        # "no data" is the legacy data-loss path.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sites.json"
            path.write_text("   \n", encoding="utf-8")
            with self.assertRaises(CorruptDataError):
                JsonFileStore(path).load()


class SaveTests(unittest.TestCase):
    def test_roundtrip_is_utf8_and_human_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sites.json"
            store = JsonFileStore(path)
            payload = [{"name": "中文名称", "note": "带中文的备注"}]
            store.save(payload)

            text = path.read_text(encoding="utf-8")
            self.assertIn("中文名称", text)
            self.assertNotIn("\\u", text)  # ensure_ascii=False
            self.assertIn('\n    "name"', text)  # indent=2 (nested one level)
            self.assertTrue(text.endswith("\n"))
            self.assertEqual(store.load(), payload)

    def test_backup_holds_the_previous_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sites.json"
            store = JsonFileStore(path)
            store.save([{"v": 1}])
            self.assertFalse(store.backup_path.exists())

            store.save([{"v": 2}])
            self.assertTrue(store.backup_path.exists())
            self.assertEqual(
                json.loads(store.backup_path.read_text(encoding="utf-8")), [{"v": 1}]
            )
            self.assertEqual(store.load(), [{"v": 2}])

    def test_no_temp_files_left_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sites.json"
            store = JsonFileStore(path)
            for i in range(3):
                store.save([{"v": i}])
            leftovers = [p.name for p in Path(tmp).iterdir() if ".tmp-" in p.name]
            self.assertEqual(leftovers, [])

    def test_creates_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "deep" / "sites.json"
            JsonFileStore(path).save([])
            self.assertTrue(path.exists())

    def test_atomic_write_failure_keeps_original(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text("original", encoding="utf-8")
            with self.assertRaises(TypeError):
                atomic_write_text(path, object())  # type: ignore[arg-type]
            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            leftovers = [p.name for p in Path(tmp).iterdir() if ".tmp-" in p.name]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
