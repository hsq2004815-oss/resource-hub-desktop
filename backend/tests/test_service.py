"""Tests for the business layer (§5.2 + §5.3 of the audit)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from resource_hub_core.models import ALL_CATEGORIES, UNCATEGORIZED
from resource_hub_core.service import (
    DuplicateError,
    ResourceService,
    ServiceError,
    ValidationError,
)
from resource_hub_core.storage import CorruptDataError


class ServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.service = ResourceService(self.dir)
        self.service.load()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_dir(self, name: str = "target") -> Path:
        path = self.dir / name
        path.mkdir(exist_ok=True)
        return path

    def make_file(self, name: str = "file.txt") -> Path:
        path = self.dir / name
        path.write_text("x", encoding="utf-8")
        return path

    def reload(self) -> ResourceService:
        service = ResourceService(self.dir)
        service.load()
        return service


class LoadTests(ServiceTestCase):
    def test_first_run_writes_sample_data(self) -> None:
        self.assertTrue((self.dir / "sites.json").exists())
        self.assertTrue((self.dir / "folders.json").exists())
        names = {item.name for item in self.service.items("links")}
        self.assertEqual(names, {"OpenAI", "GitHub"})

    def test_empty_file_stays_empty(self) -> None:
        # Legacy repopulated sample data whenever the list was empty, which
        # resurrected entries the user had deleted. ADR-001 D3 fixes that.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "sites.json").write_text("[]", encoding="utf-8")
            (path / "folders.json").write_text("[]", encoding="utf-8")
            service = ResourceService(path)
            service.load()
            self.assertEqual(service.items("links"), ())
            self.assertEqual(service.items("folders"), ())
            self.assertEqual((path / "sites.json").read_text(encoding="utf-8"), "[]")

    def test_corrupt_file_raises_and_is_left_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            broken = '[{"name": "a", '
            (path / "sites.json").write_text(broken, encoding="utf-8")
            (path / "folders.json").write_text("[]", encoding="utf-8")
            service = ResourceService(path)
            with self.assertRaises(CorruptDataError):
                service.load()
            self.assertEqual((path / "sites.json").read_text(encoding="utf-8"), broken)

    def test_non_array_payload_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "sites.json").write_text('{"name": "a"}', encoding="utf-8")
            (path / "folders.json").write_text("[]", encoding="utf-8")
            with self.assertRaises(CorruptDataError):
                ResourceService(path).load()

    def test_incomplete_entries_are_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "sites.json").write_text(
                json.dumps(
                    [
                        {"name": "ok", "url": "https://a.example"},
                        {"name": "no url"},
                        {"url": "https://b.example"},
                    ]
                ),
                encoding="utf-8",
            )
            (path / "folders.json").write_text("[]", encoding="utf-8")
            service = ResourceService(path)
            service.load()
            self.assertEqual([item.name for item in service.items("links")], ["ok"])


class AddLinkTests(ServiceTestCase):
    def test_add_normalises_and_puts_on_top(self) -> None:
        item = self.service.add("links", name="Docs", target="docs.example.com")
        self.assertEqual(item.url, "https://docs.example.com")
        self.assertEqual(item.category, UNCATEGORIZED)
        self.assertEqual(self.service.items("links")[0].id, item.id)

    def test_add_persists_immediately(self) -> None:
        self.service.add("links", name="Persisted", target="https://persisted.example")
        payload = json.loads((self.dir / "sites.json").read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["name"], "Persisted")

    def test_validation_order(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            self.service.add("links", name="  ", target="https://a.example")
        self.assertEqual(ctx.exception.key, "enter_link_name")

        with self.assertRaises(ValidationError) as ctx:
            self.service.add("links", name="A", target="   ")
        self.assertEqual(ctx.exception.key, "enter_link_path")

        with self.assertRaises(ValidationError) as ctx:
            self.service.add("links", name="A", target="ftp://a.example")
        self.assertEqual(ctx.exception.key, "invalid_link_path")

    def test_duplicate_detection_ignores_case_and_trailing_slash(self) -> None:
        self.service.add("links", name="Example", target="https://Example.TEST")
        with self.assertRaises(DuplicateError) as ctx:
            self.service.add("links", name="Again", target="https://example.test/")
        self.assertEqual(ctx.exception.key, "duplicate_link_path")

    def test_uppercase_scheme_is_rejected(self) -> None:
        # Legacy validates with a case-sensitive prefix check, so "HTTPS://x"
        # never reaches the collection. Preserved as-is for parity.
        with self.assertRaises(ValidationError) as ctx:
            self.service.add("links", name="Upper", target="HTTPS://upper.test")
        self.assertEqual(ctx.exception.key, "invalid_link_path")

    def test_duplicate_detection_also_matches_sample_data(self) -> None:
        # The first run seeds GitHub; re-adding it must be refused.
        with self.assertRaises(DuplicateError):
            self.service.add("links", name="GitHub", target="https://github.com/")

    def test_scheme_difference_is_not_a_duplicate(self) -> None:
        # Legacy compares the normalised string, so http and https are distinct.
        self.service.add("links", name="Plain", target="http://scheme.test")
        item = self.service.add("links", name="Secure", target="https://scheme.test")
        self.assertEqual(item.url, "https://scheme.test")

    def test_category_is_normalised(self) -> None:
        item = self.service.add(
            "links", name="A", target="https://a.example", category="未分类"
        )
        self.assertEqual(item.category, UNCATEGORIZED)

    def test_note_is_trimmed(self) -> None:
        item = self.service.add(
            "links", name="A", target="https://a.example", note="  hi  "
        )
        self.assertEqual(item.note, "hi")


class AddFolderTests(ServiceTestCase):
    def test_existing_directory(self) -> None:
        target = self.make_dir()
        item = self.service.add("folders", name="Dir", target=str(target))
        self.assertEqual(item.kind, "folder")
        self.assertEqual(item.path, str(target))

    def test_existing_file(self) -> None:
        target = self.make_file()
        item = self.service.add("folders", name="File", target=str(target))
        self.assertEqual(item.kind, "file")

    def test_missing_path_rejected(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            self.service.add("folders", name="Nope", target=str(self.dir / "missing"))
        self.assertEqual(ctx.exception.key, "invalid_folder_path")

    def test_duplicate_folder(self) -> None:
        target = self.make_dir()
        self.service.add("folders", name="Dir", target=str(target))
        with self.assertRaises(DuplicateError) as ctx:
            self.service.add("folders", name="Dir again", target=str(target) + os_sep())
        self.assertEqual(ctx.exception.key, "duplicate_folder_path")


def os_sep() -> str:
    return "\\" if __import__("os").name == "nt" else "/"


class UpdateTests(ServiceTestCase):
    def test_update_preserves_identity_and_favorite(self) -> None:
        item = self.service.add("links", name="Old", target="https://a.example")
        self.service.set_favorite("links", item.id, True)

        updated = self.service.update(
            "links", item.id, name="New", target="https://b.example", note="n"
        )
        self.assertEqual(updated.id, item.id)
        self.assertEqual(updated.created_at, item.created_at)
        self.assertTrue(updated.favorite)
        self.assertEqual(updated.name, "New")
        self.assertEqual(len(self.service.items("links")), 3)

    def test_update_to_same_target_is_allowed(self) -> None:
        item = self.service.add("links", name="A", target="https://a.example")
        updated = self.service.update(
            "links", item.id, name="A renamed", target="https://a.example"
        )
        self.assertEqual(updated.name, "A renamed")

    def test_update_to_another_items_target_is_rejected(self) -> None:
        first = self.service.add("links", name="A", target="https://a.example")
        self.service.add("links", name="B", target="https://b.example")
        with self.assertRaises(DuplicateError):
            self.service.update("links", first.id, name="A", target="https://b.example")


class DeleteAndFavoriteTests(ServiceTestCase):
    def test_delete(self) -> None:
        item = self.service.add("links", name="Temp", target="https://temp.example")
        self.assertTrue(self.service.delete("links", item.id))
        self.assertFalse(self.service.delete("links", item.id))
        self.assertNotIn(item.id, [entry.id for entry in self.service.items("links")])

    def test_toggle_favorite_persists(self) -> None:
        item = self.service.add("links", name="Fav", target="https://fav.example")
        self.assertTrue(self.service.toggle_favorite("links", item.id).favorite)
        self.assertTrue(self.reload().get("links", item.id).favorite)
        self.assertFalse(self.service.toggle_favorite("links", item.id).favorite)

    def test_set_favorite_is_idempotent(self) -> None:
        item = self.service.add("links", name="Fav", target="https://fav.example")
        self.assertFalse(self.service.set_favorite("links", item.id, False).favorite)


class VisibleTests(ServiceTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Clear the sample data so ordering assertions are unambiguous.
        (self.dir / "sites.json").write_text("[]", encoding="utf-8")
        (self.dir / "folders.json").write_text("[]", encoding="utf-8")
        self.service = ResourceService(self.dir)
        self.service.load()
        self.a = self.service.add("links", name="Alpha", target="https://a.example")
        self.b = self.service.add("links", name="Beta", target="https://b.example")
        self.c = self.service.add(
            "links", name="Gamma", target="https://c.example", category="开发"
        )
        self.service.set_favorite("links", self.b.id, True)

    def test_favorites_come_first_and_order_is_stable(self) -> None:
        # Insertion order after three adds is [Gamma, Beta, Alpha].
        names = [item.name for item in self.service.visible("links")]
        self.assertEqual(names, ["Beta", "Gamma", "Alpha"])

    def test_search_matches_name_target_and_note(self) -> None:
        self.assertEqual(
            [i.name for i in self.service.visible("links", query="alph")], ["Alpha"]
        )
        self.assertEqual(
            [i.name for i in self.service.visible("links", query="c.example")], ["Gamma"]
        )

    def test_search_is_case_insensitive(self) -> None:
        self.assertEqual(
            [i.name for i in self.service.visible("links", query="BETA")], ["Beta"]
        )

    def test_category_filter(self) -> None:
        result = self.service.visible("links", category="开发")
        self.assertEqual([i.name for i in result], ["Gamma"])

    def test_all_categories_sentinel_does_not_filter(self) -> None:
        self.assertEqual(len(self.service.visible("links", category=ALL_CATEGORIES)), 3)

    def test_favorites_only(self) -> None:
        result = self.service.visible("links", favorites_only=True)
        self.assertEqual([i.name for i in result], ["Beta"])

    def test_search_can_match_the_localized_uncategorized_label(self) -> None:
        # Without the injected label the backend has no idea what "未分类" means.
        self.assertEqual(self.service.visible("links", query="未分类"), ())
        result = self.service.visible(
            "links", query="未分类", uncategorized_label="未分类"
        )
        self.assertEqual(sorted(i.name for i in result), ["Alpha", "Beta"])

    def test_categories_excludes_sentinel(self) -> None:
        self.assertEqual(self.service.categories("links"), ("开发",))


class PathCheckTests(ServiceTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Start from empty collections so only the entries we create are checked.
        (self.dir / "sites.json").write_text("[]", encoding="utf-8")
        (self.dir / "folders.json").write_text("[]", encoding="utf-8")
        self.service = ResourceService(self.dir)
        self.service.load()

    def test_links_are_not_supported(self) -> None:
        result = self.service.check_paths("links")
        self.assertFalse(result.supported)
        self.assertEqual(result.missing_count, 0)

    def test_missing_folder_is_reported(self) -> None:
        target = self.make_dir("doomed")
        item = self.service.add("folders", name="Doomed", target=str(target))
        target.rmdir()

        result = self.service.check_paths("folders")
        self.assertTrue(result.supported)
        self.assertIn(item.id, result.missing)
        self.assertEqual(result.missing_count, 1)


class DropTests(ServiceTestCase):
    def test_counts_added_skipped_and_invalid(self) -> None:
        target = self.make_dir("dropped")
        result = self.service.add_dropped(
            [str(target), str(target), str(self.dir / "nope"), ""]
        )
        self.assertEqual(result.added, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.invalid, 2)

    def test_dropped_item_uses_folder_name(self) -> None:
        target = self.make_dir("my-folder")
        self.service.add_dropped([str(target)])
        self.assertEqual(self.service.items("folders")[0].name, "my-folder")

    def test_dropped_item_is_persisted(self) -> None:
        target = self.make_dir("persisted")
        self.service.add_dropped([str(target)])
        self.assertEqual(self.reload().items("folders")[0].name, "persisted")


class BackupTests(ServiceTestCase):
    def test_export_then_import_roundtrip(self) -> None:
        payload = self.service.export_payload("links")
        self.assertEqual(len(payload), 2)
        self.assertIn("url", payload[0])

        result = self.service.import_payload("links", payload)
        self.assertEqual(result.imported, 2)
        self.assertEqual(result.skipped, 0)

    def test_import_replaces_rather_than_merges(self) -> None:
        payload = [{"name": "Only", "url": "https://only.example"}]
        self.service.import_payload("links", payload)
        self.assertEqual([i.name for i in self.service.items("links")], ["Only"])

    def test_import_dedupes_within_payload(self) -> None:
        payload = [
            {"name": "A", "url": "https://dup.example"},
            {"name": "B", "url": "HTTPS://DUP.example/"},
        ]
        result = self.service.import_payload("links", payload)
        self.assertEqual(result.imported, 1)
        self.assertEqual(result.skipped, 1)

    def test_import_drops_incomplete_entries(self) -> None:
        payload = [{"name": "ok", "url": "https://ok.example"}, {"name": "bad"}]
        result = self.service.import_payload("links", payload)
        self.assertEqual(result.imported, 1)

    def test_import_rejects_non_array(self) -> None:
        with self.assertRaises(ServiceError) as ctx:
            self.service.import_payload("links", {"name": "x"})
        self.assertEqual(ctx.exception.key, "import_failed")


class CategoryRenameTests(ServiceTestCase):
    def setUp(self) -> None:
        super().setUp()
        (self.dir / "sites.json").write_text("[]", encoding="utf-8")
        (self.dir / "folders.json").write_text("[]", encoding="utf-8")
        self.service = ResourceService(self.dir)
        self.service.load()

    def test_rename_merges_into_target(self) -> None:
        self.service.add("links", name="A", target="https://a.example", category="Old")
        self.service.add("links", name="B", target="https://b.example", category="Old")
        changed = self.service.rename_category("links", "Old", "New")
        self.assertEqual(changed, 2)
        self.assertEqual(self.service.categories("links"), ("New",))


if __name__ == "__main__":
    unittest.main()
