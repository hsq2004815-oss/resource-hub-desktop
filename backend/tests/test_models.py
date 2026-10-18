"""Tests for the JSON contract models (§5.2 of the audit)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from resource_hub_core.models import (
    UNCATEGORIZED,
    Folder,
    Site,
    is_complete,
    normalize_category,
    parse_entry,
)


class CategoryTests(unittest.TestCase):
    def test_blank_becomes_sentinel(self) -> None:
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.assertEqual(normalize_category(value), UNCATEGORIZED)

    def test_legacy_uncategorized_labels_become_sentinel(self) -> None:
        for value in ("未分类", "Uncategorized"):
            with self.subTest(value=value):
                self.assertEqual(normalize_category(value), UNCATEGORIZED)

    def test_real_category_is_kept(self) -> None:
        self.assertEqual(normalize_category(" 开发 "), "开发")


class SiteTests(unittest.TestCase):
    def test_normalize_fills_required_fields(self) -> None:
        site = Site.normalize({"name": "GitHub", "url": "github.com"})
        self.assertTrue(site.id)
        self.assertEqual(site.url, "https://github.com")
        self.assertEqual(site.category, UNCATEGORIZED)
        self.assertFalse(site.favorite)
        self.assertTrue(site.created_at)

    def test_normalize_keeps_existing_values(self) -> None:
        raw = {
            "id": "fixed-id",
            "name": "Docs",
            "url": "https://docs.example.com/",
            "category": "文档",
            "note": "keep me",
            "favorite": True,
            "createdAt": "2026-04-22T13:53:49+08:00",
        }
        site = Site.normalize(raw)
        self.assertEqual(site.to_json(), raw)

    def test_favorite_uses_legacy_truthiness(self) -> None:
        # bool("false") is True; this is the legacy behaviour and is preserved so
        # existing files load identically. The client always sends real booleans.
        self.assertTrue(Site.normalize({"name": "a", "url": "b", "favorite": "false"}).favorite)

    def test_is_complete_requires_name_and_url(self) -> None:
        self.assertTrue(Site.is_complete({"name": "a", "url": "b"}))
        self.assertFalse(Site.is_complete({"name": "a"}))
        self.assertFalse(Site.is_complete({"url": "b"}))
        self.assertFalse(Site.is_complete({"name": "", "url": "b"}))


class FolderTests(unittest.TestCase):
    def test_accepts_legacy_url_field(self) -> None:
        folder = Folder.normalize({"name": "old", "url": r"D:\somewhere"})
        self.assertEqual(folder.path, r"D:\somewhere")

    def test_kind_inferred_from_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "adir"
            directory.mkdir()
            file = Path(tmp) / "afile.txt"
            file.write_text("x", encoding="utf-8")

            self.assertEqual(Folder.normalize({"name": "d", "path": str(directory)}).kind, "folder")
            self.assertEqual(Folder.normalize({"name": "f", "path": str(file)}).kind, "file")

    def test_missing_path_defaults_to_file(self) -> None:
        folder = Folder.normalize({"name": "gone", "path": r"D:\definitely\missing\path"})
        self.assertEqual(folder.kind, "file")

    def test_explicit_kind_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Folder.normalize({"name": "d", "path": tmp, "kind": "file"})
            self.assertEqual(folder.kind, "file")

    def test_is_complete_accepts_path_or_url(self) -> None:
        self.assertTrue(Folder.is_complete({"name": "a", "path": "p"}))
        self.assertTrue(Folder.is_complete({"name": "a", "url": "p"}))
        self.assertFalse(Folder.is_complete({"name": "a"}))
        self.assertFalse(Folder.is_complete({"path": "p"}))


class ParseEntryTests(unittest.TestCase):
    def test_dispatch_by_mode(self) -> None:
        self.assertIsInstance(parse_entry("links", {"name": "a", "url": "b"}), Site)
        self.assertIsInstance(parse_entry("folders", {"name": "a", "path": "b"}), Folder)

    def test_unknown_mode_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_entry("bookmarks", {"name": "a"})
        with self.assertRaises(ValueError):
            is_complete("bookmarks", {"name": "a"})


if __name__ == "__main__":
    unittest.main()
