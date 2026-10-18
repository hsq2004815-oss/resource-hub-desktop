"""Tests for the read-only filesystem browsing used by the preview panel."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from resource_hub_core.fs import FsError, list_children, open_fs_path, reveal_fs_path


class FsListingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_dir(self, name: str) -> Path:
        path = self.dir / name
        path.mkdir()
        return path

    def make_file(self, name: str) -> Path:
        path = self.dir / name
        path.write_text("x", encoding="utf-8")
        return path

    def test_sorts_folders_first_then_names_case_insensitively(self) -> None:
        self.make_file("zeta.txt")
        self.make_dir("beta")
        self.make_file("readme.md")
        self.make_dir("Alpha")

        listing = list_children(str(self.dir))

        self.assertEqual([entry.name for entry in listing.entries],
                         ["Alpha", "beta", "readme.md", "zeta.txt"])
        self.assertEqual([entry.kind for entry in listing.entries],
                         ["folder", "folder", "file", "file"])
        self.assertEqual(listing.total, 4)
        self.assertFalse(listing.truncated)

    def test_entry_paths_are_absolute_and_flags_default_false(self) -> None:
        folder = self.make_dir("project")
        listing = list_children(str(self.dir))
        entry = listing.entries[0]
        self.assertEqual(entry.path, str(folder))
        self.assertFalse(entry.is_link)

    def test_unicode_names_roundtrip(self) -> None:
        self.make_dir("设计稿")
        self.make_file("说明.md")
        listing = list_children(str(self.dir))
        self.assertEqual([entry.name for entry in listing.entries], ["设计稿", "说明.md"])

    def test_empty_directory(self) -> None:
        listing = list_children(str(self.dir))
        self.assertEqual(listing.entries, ())
        self.assertEqual(listing.total, 0)
        self.assertFalse(listing.truncated)

    def test_missing_path_reports_fs_not_found(self) -> None:
        with self.assertRaises(FsError) as ctx:
            list_children(str(self.dir / "nope"))
        self.assertEqual(ctx.exception.key, "fs_not_found")

    def test_file_is_not_a_directory(self) -> None:
        target = self.make_file("note.txt")
        with self.assertRaises(FsError) as ctx:
            list_children(str(target))
        self.assertEqual(ctx.exception.key, "fs_not_directory")

    def test_empty_path_is_rejected(self) -> None:
        with self.assertRaises(FsError) as ctx:
            list_children("   ")
        self.assertEqual(ctx.exception.key, "fs_not_found")

    def test_large_directory_is_capped_but_counted(self) -> None:
        for index in range(210):
            (self.dir / f"file-{index:03d}.txt").write_text("x", encoding="utf-8")

        listing = list_children(str(self.dir))

        self.assertEqual(listing.shown, 200)
        self.assertEqual(listing.total, 210)
        self.assertTrue(listing.truncated)

    def test_symlink_is_flagged_when_supported(self) -> None:
        target = self.make_dir("target")
        link = self.dir / "link"
        try:
            os.symlink(target, link, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")

        listing = list_children(str(self.dir))
        by_name = {entry.name: entry for entry in listing.entries}
        self.assertTrue(by_name["link"].is_link)
        self.assertEqual(by_name["link"].kind, "folder")

    def test_open_and_reveal_validate_then_delegate(self) -> None:
        folder = self.make_dir("open-me")
        with mock.patch("resource_hub_core.fs.open_path") as opener:
            open_fs_path(str(folder))
        opener.assert_called_once_with(str(folder))

        with mock.patch("resource_hub_core.fs.reveal_path") as revealer:
            reveal_fs_path(str(folder))
        revealer.assert_called_once_with(str(folder))

        with self.assertRaises(FsError) as ctx:
            open_fs_path(str(self.dir / "gone"))
        self.assertEqual(ctx.exception.key, "fs_not_found")


if __name__ == "__main__":
    unittest.main()
