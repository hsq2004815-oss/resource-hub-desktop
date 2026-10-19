"""Tests for the Chrome/Edge bookmark bridge (Phase 17).

The real browser data directories are never touched: every test points
``RH_BROWSER_DATA_DIRS`` at a temporary fixture, which is exactly the override
the production code documents for portable installs.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Mapping
from unittest import mock

from resource_hub_core.bookmarks import (
    BOOKMARK_BAR_CATEGORY,
    BROWSER_DATA_DIRS_ENV,
    OTHER_BOOKMARKS_CATEGORY,
    READ_RETRY_DELAY_SECONDS,
    BookmarkSyncEngine,
    BookmarkWatcher,
    collect_bookmarks,
    dedup_key,
    discover_profiles,
    normalize_bookmark_url,
    parse_bookmarks,
)
from resource_hub_core.protocol import JsonLinesServer
from resource_hub_core.service import (
    ORDER_META_FILENAME,
    ORDER_VERSION,
    ResourceService,
)
from resource_hub_core.settings import Settings

CUSTOM_LABEL = "自定义"


# --- fixture helpers -------------------------------------------------------
def url_node(name: str, url: str) -> dict[str, Any]:
    return {"type": "url", "name": name, "url": url}


def folder_node(name: str, children: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "folder", "name": name, "children": children}


def bookmarks_document(
    bar: list[dict[str, Any]] | None = None,
    other: list[dict[str, Any]] | None = None,
    synced: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    roots: dict[str, Any] = {
        "bookmark_bar": folder_node("Bookmarks bar", bar or []),
    }
    if other is not None:
        roots["other"] = folder_node("Other bookmarks", other)
    if synced is not None:
        roots["synced"] = folder_node("Mobile bookmarks", synced)
    return {"roots": roots}


def write_profile(
    root: Path,
    profile: str,
    payload: Mapping[str, Any],
    filename: str = "Bookmarks",
) -> Path:
    directory = root / profile
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def sync_fixture_document() -> dict[str, Any]:
    """Five accepted bookmarks with nested folders, used by the sync tests."""
    return bookmarks_document(
        bar=[
            url_node("Home", "https://home.example/"),
            folder_node(
                "开发",
                [
                    url_node("Python", "https://python.org/"),
                    folder_node("工具", [url_node("PyPI", "https://pypi.org/")]),
                ],
            ),
        ],
        other=[url_node("Docs", "https://docs.example/")],
        synced=[url_node("Mobile", "https://mobile.example/")],
    )


def mixed_document() -> dict[str, Any]:
    """Accepted bookmarks plus every scheme/edge case that must be filtered."""
    return bookmarks_document(
        bar=[
            url_node("Home", "https://home.example/"),
            folder_node(
                "开发",
                [
                    url_node("Python", "https://python.org/"),
                    folder_node("工具", [url_node("GitHub", "https://github.com/")]),
                    url_node("Chrome Pages", "chrome://bookmarks/"),
                    url_node("Edge Pages", "edge://settings/"),
                    url_node("Script", "javascript:void(0)"),
                    url_node("Data", "data:text/html,hello"),
                    url_node("Local", "file:///C:/secret.txt"),
                    url_node("About", "about:blank"),
                    url_node("FTP", "ftp://files.example/"),
                ],
            ),
            url_node("Home again", "https://home.example"),
            url_node("", "https://nameless.example/page"),
        ],
        other=[
            url_node("Docs", "https://docs.example/"),
            folder_node("阅读", [url_node("Blog", "https://blog.example/")]),
        ],
        synced=[url_node("Mobile", "https://mobile.example/")],
    )


def sample_entries() -> list[tuple[str, str, str, str]]:
    """Expected ``(label, name, url, category)`` order for ``mixed_document``."""
    return [
        ("Chrome · Default", "Home", "https://home.example/", BOOKMARK_BAR_CATEGORY),
        ("Chrome · Default", "Python", "https://python.org/", "开发"),
        ("Chrome · Default", "GitHub", "https://github.com/", "开发/工具"),
        ("Chrome · Default", "Home again", "https://home.example", BOOKMARK_BAR_CATEGORY),
        (
            "Chrome · Default",
            "nameless.example",
            "https://nameless.example/page",
            BOOKMARK_BAR_CATEGORY,
        ),
        ("Chrome · Default", "Docs", "https://docs.example/", OTHER_BOOKMARKS_CATEGORY),
        ("Chrome · Default", "Blog", "https://blog.example/", "阅读"),
        ("Chrome · Default", "Mobile", "https://mobile.example/", OTHER_BOOKMARKS_CATEGORY),
    ]


class EnvFixtureTestCase(unittest.TestCase):
    """Temporary browser root shared by the discovery tests."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.data = self.base / "browser"
        self.chrome_root = self.data / "Chrome"
        self.edge_root = self.data / "Edge"
        self._env = mock.patch.dict(
            os.environ, {BROWSER_DATA_DIRS_ENV: str(self.chrome_root)}
        )
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()


# --- URL handling ----------------------------------------------------------
class UrlNormalizationTests(unittest.TestCase):
    def test_only_http_and_https_survive(self) -> None:
        accepted = {
            "https://home.example/": "https://home.example/",
            "http://plain.example": "http://plain.example",
            "  https://trimmed.example  ": "https://trimmed.example",
            "HTTPS://Upper.Example/Path": "https://Upper.Example/Path",
        }
        for raw, expected in accepted.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_bookmark_url(raw), expected)

        for raw in (
            "",
            "   ",
            "chrome://bookmarks/",
            "edge://settings/",
            "about:blank",
            "javascript:void(0)",
            "data:text/html,hello",
            "file:///C:/secret.txt",
            "ftp://files.example/",
            "mailto:someone@example.com",
            "home.example",
        ):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_bookmark_url(raw))

    def test_dedup_key_ignores_case_trailing_slashes_and_space(self) -> None:
        key = dedup_key(" https://Home.Example/Path/ ")
        self.assertEqual(key, "https://home.example/path")
        self.assertEqual(key, dedup_key("https://home.example/path"))
        self.assertEqual(dedup_key("https://home.example///"), "https://home.example")


# --- parsing ---------------------------------------------------------------
class ParseBookmarksTests(EnvFixtureTestCase):
    def test_categories_order_and_filters(self) -> None:
        path = write_profile(self.chrome_root, "Default", mixed_document())

        parsed = parse_bookmarks(path)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        label = "Chrome · Default"
        self.assertEqual(
            [(label, entry.name, entry.url, entry.category) for entry in parsed],
            sample_entries(),
        )

    def test_bookmarks_are_imported_per_top_level_root(self) -> None:
        # Direct bar children use the bar category; other/synced children share
        # the "other bookmarks" one. Nested folders replace it with the path.
        write_profile(self.chrome_root, "Default", mixed_document())
        collection = collect_bookmarks(Settings())

        self.assertEqual(collection.total, len(sample_entries()))
        self.assertEqual([entry[3] for entry in collection.entries][:3],
                         [BOOKMARK_BAR_CATEGORY, "开发", "开发/工具"])
        self.assertEqual(collection.entries[-1][3], OTHER_BOOKMARKS_CATEGORY)

    def test_empty_name_falls_back_to_host_then_url(self) -> None:
        document = bookmarks_document(
            bar=[url_node("", "https://nameless.example/page/path")]
        )
        collection = collect_bookmarks(Settings())
        write_profile(self.chrome_root, "Default", document)
        collection = collect_bookmarks(Settings())

        self.assertEqual(collection.entries[0][1], "nameless.example")

    def test_malformed_json_returns_no_entries_and_does_not_raise(self) -> None:
        profile = self.chrome_root / "Default"
        profile.mkdir(parents=True)
        path = profile / "Bookmarks"
        path.write_text("{not valid json", encoding="utf-8")

        self.assertIsNone(parse_bookmarks(path))
        collection = collect_bookmarks(Settings())
        self.assertEqual(collection.entries, ())
        self.assertEqual(collection.total, 0)
        self.assertEqual(collection.profiles, ())

    def test_mid_write_read_is_retried_once(self) -> None:
        valid = json.dumps(mixed_document())
        with (
            mock.patch(
                "pathlib.Path.read_text", side_effect=["{half a file", valid]
            ),
            mock.patch("resource_hub_core.bookmarks.time.sleep") as sleeper,
        ):
            parsed = parse_bookmarks(Path("ignored") / "Bookmarks")

        self.assertIsNotNone(parsed)
        sleeper.assert_called_once_with(READ_RETRY_DELAY_SECONDS)

    def test_two_bad_reads_are_treated_as_unreadable(self) -> None:
        with (
            mock.patch(
                "pathlib.Path.read_text", side_effect=["{half", "still broken"]
            ),
            mock.patch("resource_hub_core.bookmarks.time.sleep") as sleeper,
        ):
            parsed = parse_bookmarks(Path("ignored") / "Bookmarks")

        self.assertIsNone(parsed)
        sleeper.assert_called_once_with(READ_RETRY_DELAY_SECONDS)


# --- discovery -------------------------------------------------------------
class ProfileDiscoveryTests(EnvFixtureTestCase):
    def test_profiles_are_ordered_default_then_profile_number(self) -> None:
        payload = sync_fixture_document()
        for profile in ("Default", "Profile 1", "Profile 2", "Profile 10"):
            write_profile(self.chrome_root, profile, payload)
        # Neither a profile without Bookmarks nor an unrelated directory is one.
        (self.chrome_root / "Profile 3").mkdir()
        (self.chrome_root / "Crash Reports").mkdir()

        profiles = discover_profiles(Settings())

        self.assertEqual(
            [profile.label for profile in profiles],
            [
                "Chrome · Default",
                "Chrome · Profile 1",
                "Chrome · Profile 2",
                "Chrome · Profile 10",
            ],
        )
        self.assertEqual(len({profile.path for profile in profiles}), 4)

    def test_account_bookmarks_profile_is_discovered(self) -> None:
        path = write_profile(
            self.chrome_root, "Profile 1", sync_fixture_document(), "AccountBookmarks"
        )

        profiles = discover_profiles(Settings())

        self.assertEqual([profile.label for profile in profiles], ["Chrome · Profile 1"])
        self.assertEqual(list(profiles[0].paths), [path])

    def test_account_and_local_bookmarks_are_merged_per_profile(self) -> None:
        local = write_profile(self.chrome_root, "Default", mixed_document())
        account = write_profile(
            self.chrome_root, "Default", sync_fixture_document(), "AccountBookmarks"
        )

        profiles = discover_profiles(Settings())

        self.assertEqual([profile.label for profile in profiles], ["Chrome · Default"])
        self.assertEqual(set(profiles[0].paths), {account, local})
        # Both files are parsed; sync de-duplicates the overlapping URLs.
        self.assertEqual(collect_bookmarks(Settings()).total, 13)

    def test_browsers_are_ordered_chrome_then_edge(self) -> None:
        self._env.stop()
        self._env = mock.patch.dict(
            os.environ,
            {
                BROWSER_DATA_DIRS_ENV: os.pathsep.join(
                    [str(self.chrome_root), str(self.edge_root)]
                )
            },
        )
        self._env.start()
        write_profile(self.chrome_root, "Default", sync_fixture_document())
        write_profile(self.edge_root, "Default", sync_fixture_document())

        profiles = discover_profiles(Settings())

        self.assertEqual(
            [profile.label for profile in profiles],
            ["Chrome · Default", "Edge · Default"],
        )

    def test_env_override_with_empty_value_discovers_nothing(self) -> None:
        write_profile(self.chrome_root, "Default", sync_fixture_document())
        with mock.patch.dict(os.environ, {BROWSER_DATA_DIRS_ENV: ""}):
            self.assertEqual(discover_profiles(Settings()), [])

    def test_env_override_replaces_the_default_roots(self) -> None:
        write_profile(self.chrome_root, "Default", sync_fixture_document())
        local_app_data = self.base / "LocalAppData"
        with mock.patch.dict(
            os.environ,
            {BROWSER_DATA_DIRS_ENV: str(self.chrome_root / "missing")},
        ):
            (local_app_data / "Google" / "Chrome" / "User Data").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
                self.assertEqual(discover_profiles(Settings()), [])

    def test_default_roots_use_local_app_data(self) -> None:
        local_app_data = self.base / "LocalAppData"
        chrome = local_app_data / "Google" / "Chrome" / "User Data"
        edge = local_app_data / "Microsoft" / "Edge" / "User Data"
        write_profile(chrome, "Default", sync_fixture_document())
        write_profile(edge, "Default", sync_fixture_document())
        os.environ.pop(BROWSER_DATA_DIRS_ENV, None)

        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
            profiles = discover_profiles(Settings())

        self.assertEqual(
            [profile.label for profile in profiles],
            ["Chrome · Default", "Edge · Default"],
        )

    def test_missing_roots_are_skipped(self) -> None:
        with mock.patch.dict(
            os.environ, {BROWSER_DATA_DIRS_ENV: str(self.base / "nothing-here")}
        ):
            self.assertEqual(discover_profiles(Settings()), [])


class CustomDirectoryTests(EnvFixtureTestCase):
    def test_bookmarks_file_path(self) -> None:
        path = write_profile(self.base / "custom", "Profile X", sync_fixture_document())

        profiles = discover_profiles(Settings(bookmark_custom_dir=str(path)))

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].label, CUSTOM_LABEL)
        self.assertEqual(profiles[0].path, path)

    def test_profile_directory_containing_bookmarks(self) -> None:
        write_profile(self.base / "custom", "Profile X", sync_fixture_document())
        directory = self.base / "custom" / "Profile X"

        profiles = discover_profiles(Settings(bookmark_custom_dir=str(directory)))

        self.assertEqual([profile.label for profile in profiles], [CUSTOM_LABEL])

    def test_account_bookmarks_file_path(self) -> None:
        path = write_profile(
            self.base / "custom",
            "Profile X",
            sync_fixture_document(),
            "AccountBookmarks",
        )

        profiles = discover_profiles(Settings(bookmark_custom_dir=str(path)))

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].label, CUSTOM_LABEL)
        self.assertEqual(profiles[0].path, path)

    def test_user_data_directory_scans_profiles(self) -> None:
        root = self.base / "custom"
        write_profile(root, "Default", sync_fixture_document())
        write_profile(root, "Profile 1", sync_fixture_document())

        profiles = discover_profiles(Settings(bookmark_custom_dir=str(root)))

        self.assertEqual(
            [profile.label for profile in profiles],
            [f"{CUSTOM_LABEL} · Default", f"{CUSTOM_LABEL} · Profile 1"],
        )

    def test_missing_or_invalid_custom_dir_is_ignored(self) -> None:
        missing = self.base / "no-such-dir"
        other_file = self.base / "notes.txt"
        other_file.write_text("x", encoding="utf-8")
        for value in ("", "   ", str(missing), str(other_file)):
            with self.subTest(value=value):
                self.assertEqual(
                    discover_profiles(Settings(bookmark_custom_dir=value)), []
                )

    def test_custom_dir_duplicating_a_browser_profile_is_not_imported_twice(self) -> None:
        path = write_profile(self.chrome_root, "Default", sync_fixture_document())

        profiles = discover_profiles(Settings(bookmark_custom_dir=str(path)))

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].label, "Chrome · Default")


# --- sync engine -----------------------------------------------------------
class BookmarkSyncEngineTests(EnvFixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.app_dir = self.base / "app"
        self.service = ResourceService(self.app_dir)
        self.service.load()
        self.engine = BookmarkSyncEngine(self.app_dir)
        self.settings = Settings()

    def _meta(self) -> dict[str, Any]:
        return json.loads(
            (self.app_dir / ORDER_META_FILENAME).read_text(encoding="utf-8")
        )

    def test_first_sync_imports_everything_at_the_end(self) -> None:
        write_profile(self.chrome_root, "Default", sync_fixture_document())
        before = [item.id for item in self.service.items("links")]

        result = self.engine.sync(self.service, self.settings)

        self.assertEqual(result["added"], 5)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["total"], 5)
        self.assertIsInstance(result["lastSyncAt"], str)
        self.assertEqual(result["profiles"][0]["label"], "Chrome · Default")
        self.assertEqual(result["profiles"][0]["bookmarks"], 5)

        items = self.service.items("links")
        self.assertEqual([item.id for item in items[:2]], before)
        self.assertEqual(
            [item.name for item in items[2:]],
            ["Home", "Python", "PyPI", "Docs", "Mobile"],
        )
        # Categories survive the round trip into sites.json.
        by_name = {item.name: item for item in items}
        self.assertEqual(by_name["Home"].category, BOOKMARK_BAR_CATEGORY)
        self.assertEqual(by_name["PyPI"].category, "开发/工具")
        self.assertEqual(by_name["Docs"].category, OTHER_BOOKMARKS_CATEGORY)

        stored = json.loads((self.app_dir / "sites.json").read_text(encoding="utf-8"))
        stored_names = [entry["name"] for entry in stored]
        self.assertEqual(stored_names[-1], "Mobile")

    def test_second_sync_adds_nothing(self) -> None:
        write_profile(self.chrome_root, "Default", sync_fixture_document())
        self.engine.sync(self.service, self.settings)
        count = len(self.service.items("links"))

        result = self.engine.sync(self.service, self.settings)

        self.assertEqual(result["added"], 0)
        self.assertEqual(result["skipped"], result["total"])
        self.assertEqual(len(self.service.items("links")), count)

    def test_deleted_resource_is_not_resurrected(self) -> None:
        write_profile(self.chrome_root, "Default", sync_fixture_document())
        self.engine.sync(self.service, self.settings)
        imported = next(
            item for item in self.service.items("links") if item.name == "Python"
        )
        self.assertTrue(self.service.delete("links", imported.id))

        result = self.engine.sync(self.service, self.settings)

        self.assertEqual(result["added"], 0)
        self.assertNotIn("Python", [item.name for item in self.service.items("links")])

    def test_bookmark_added_later_is_imported_on_the_next_sync(self) -> None:
        write_profile(self.chrome_root, "Default", sync_fixture_document())
        self.engine.sync(self.service, self.settings)
        document = sync_fixture_document()
        document["roots"]["bookmark_bar"]["children"].append(
            url_node("Later", "https://later.example/")
        )
        write_profile(self.chrome_root, "Default", document)

        result = self.engine.sync(self.service, self.settings)

        self.assertEqual(result["added"], 1)
        self.assertEqual(self.service.items("links")[-1].name, "Later")

    def test_duplicate_url_across_profiles_is_imported_once(self) -> None:
        self._env.stop()
        self._env = mock.patch.dict(
            os.environ,
            {
                BROWSER_DATA_DIRS_ENV: os.pathsep.join(
                    [str(self.chrome_root), str(self.edge_root)]
                )
            },
        )
        self._env.start()
        document = bookmarks_document(bar=[url_node("Home", "https://home.example/")])
        write_profile(self.chrome_root, "Default", document)
        write_profile(self.edge_root, "Default", document)

        result = self.engine.sync(self.service, self.settings)

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["skipped"], 1)

    def test_duplicate_url_within_one_file_is_imported_once(self) -> None:
        document = bookmarks_document(
            bar=[
                url_node("First", "https://same.example/"),
                url_node("Second", "https://SAME.example"),
            ]
        )
        write_profile(self.chrome_root, "Default", document)

        result = self.engine.sync(self.service, self.settings)

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["added"], 1)

    def test_meta_preserves_existing_keys(self) -> None:
        (self.app_dir / ORDER_META_FILENAME).write_text(
            json.dumps({"orderVersion": ORDER_VERSION, "custom": {"keep": True}}),
            encoding="utf-8",
        )
        write_profile(self.chrome_root, "Default", sync_fixture_document())

        self.engine.sync(self.service, self.settings)

        meta = self._meta()
        self.assertEqual(meta["orderVersion"], ORDER_VERSION)
        self.assertEqual(meta["custom"], {"keep": True})
        self.assertEqual(len(meta["bookmarks"]["seenUrls"]), 5)
        self.assertIsInstance(meta["bookmarks"]["lastSyncAt"], str)

    def test_corrupt_meta_starts_empty_and_is_repaired(self) -> None:
        (self.app_dir / ORDER_META_FILENAME).write_text("{not json", encoding="utf-8")
        write_profile(self.chrome_root, "Default", sync_fixture_document())

        result = self.engine.sync(self.service, self.settings)

        self.assertEqual(result["added"], 5)
        meta = self._meta()
        # The order migration marker must not be lost: an absent orderVersion
        # would re-pin favourites and destroy a manually arranged order.
        self.assertEqual(meta["orderVersion"], ORDER_VERSION)
        self.assertEqual(len(meta["bookmarks"]["seenUrls"]), 5)

    def test_sync_only_reads_browser_files(self) -> None:
        path = write_profile(self.chrome_root, "Default", sync_fixture_document())
        before = path.read_bytes()

        self.engine.sync(self.service, self.settings)

        self.assertEqual(path.read_bytes(), before)

    def test_empty_environment_syncs_nothing(self) -> None:
        result = self.engine.sync(self.service, self.settings)

        self.assertEqual(result["added"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["profiles"], [])
        # No browser found: the sync must not stamp a "last sync" time.
        self.assertIsNone(result["lastSyncAt"])
        self.assertEqual(self.engine.status(self.settings)["syncedUrls"], 0)

    def test_custom_dir_is_used_by_sync(self) -> None:
        path = write_profile(self.base / "custom", "Profile X", sync_fixture_document())
        settings = Settings(bookmark_custom_dir=str(path))

        result = self.engine.sync(self.service, settings)

        self.assertEqual(result["added"], 5)


class BookmarkStatusTests(EnvFixtureTestCase):
    def test_status_is_read_only_on_an_empty_data_dir(self) -> None:
        app_dir = self.base / "app"
        app_dir.mkdir()
        engine = BookmarkSyncEngine(app_dir)

        result = engine.status(Settings())

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
        self.assertFalse((app_dir / ORDER_META_FILENAME).exists())

    def test_status_reports_profiles_and_sync_state(self) -> None:
        app_dir = self.base / "app"
        service = ResourceService(app_dir)
        service.load()
        engine = BookmarkSyncEngine(app_dir)
        settings = Settings(bookmark_sync_enabled=False)
        write_profile(self.chrome_root, "Default", sync_fixture_document())

        before = engine.status(settings)
        self.assertFalse(before["enabled"])
        self.assertEqual(before["customDir"], "")
        self.assertEqual(before["profiles"][0]["label"], "Chrome · Default")
        self.assertEqual(before["profiles"][0]["bookmarks"], 5)
        self.assertIsNone(before["lastSyncAt"])
        self.assertEqual(before["syncedUrls"], 0)

        engine.sync(service, settings)
        after = engine.status(settings)
        self.assertIsInstance(after["lastSyncAt"], str)
        self.assertEqual(after["syncedUrls"], 5)


# --- watcher ---------------------------------------------------------------
class BookmarkWatcherTests(EnvFixtureTestCase):
    def _service(self) -> tuple[ResourceService, BookmarkSyncEngine]:
        app_dir = self.base / "app"
        service = ResourceService(app_dir)
        service.load()
        return service, BookmarkSyncEngine(app_dir)

    def test_watcher_imports_a_change(self) -> None:
        path = write_profile(self.chrome_root, "Default", sync_fixture_document())
        service, engine = self._service()
        synced: list[dict[str, Any]] = []
        watcher = BookmarkWatcher(
            engine,
            service,
            lambda: Settings(),
            synced.append,
            interval=0.05,
            rediscover_interval=0.1,
            lock=threading.RLock(),
        )
        try:
            watcher.start()
            # Wait for the first poll: it imports the fixture and captures the
            # baseline (a fixed sleep would be flaky on a loaded machine).
            baseline_deadline = time.monotonic() + 5.0
            while watcher._watched is None and time.monotonic() < baseline_deadline:
                time.sleep(0.01)
            self.assertIsNotNone(watcher._watched, "watcher never polled")
            document = sync_fixture_document()
            document["roots"]["bookmark_bar"]["children"].append(
                url_node("Watched", "https://watched.example/")
            )
            path.write_text(json.dumps(document), encoding="utf-8")

            deadline = time.monotonic() + 5.0
            while (
                "Watched" not in [item.name for item in service.items("links")]
                and time.monotonic() < deadline
            ):
                time.sleep(0.02)
        finally:
            watcher.stop()

        self.assertTrue(synced, "watcher never reported a sync")
        self.assertGreaterEqual(synced[0]["added"], 1)
        self.assertIn("Watched", [item.name for item in service.items("links")])
        self.assertFalse(watcher.running)

    def test_watcher_does_not_poll_when_disabled(self) -> None:
        path = write_profile(self.chrome_root, "Default", sync_fixture_document())
        service, engine = self._service()
        synced: list[dict[str, Any]] = []
        watcher = BookmarkWatcher(
            engine,
            service,
            lambda: Settings(bookmark_sync_enabled=False),
            synced.append,
            interval=0.05,
            rediscover_interval=0.1,
        )
        try:
            watcher.start()
            time.sleep(0.2)
            document = sync_fixture_document()
            document["roots"]["bookmark_bar"]["children"].append(
                url_node("Ignored", "https://ignored.example/")
            )
            path.write_text(json.dumps(document), encoding="utf-8")
            time.sleep(0.3)
        finally:
            watcher.stop()

        self.assertEqual(synced, [])
        self.assertNotIn("Ignored", [item.name for item in service.items("links")])

    def test_watcher_starts_and_stops_promptly(self) -> None:
        write_profile(self.chrome_root, "Default", sync_fixture_document())
        service, engine = self._service()
        watcher = BookmarkWatcher(engine, service, lambda: Settings(), lambda _: None)
        watcher.start()
        self.assertTrue(watcher.running)

        started = time.monotonic()
        watcher.stop()
        watcher.stop()  # idempotent

        self.assertFalse(watcher.running)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_a_broken_settings_getter_does_not_kill_the_watcher(self) -> None:
        service, engine = self._service()

        def explode() -> Settings:
            raise RuntimeError("boom")

        watcher = BookmarkWatcher(
            engine, service, explode, lambda _: None, interval=0.02
        )
        try:
            watcher.start()
            time.sleep(0.15)
            self.assertTrue(watcher.running)
        finally:
            watcher.stop()


    def test_first_poll_imports_existing_bookmarks(self) -> None:
        write_profile(self.chrome_root, "Default", sync_fixture_document())
        service, engine = self._service()
        watcher = BookmarkWatcher(
            engine,
            service,
            lambda: Settings(),
            lambda _: None,
            interval=0.02,
            rediscover_interval=0.05,
        )
        try:
            watcher.start()
            deadline = time.monotonic() + 5.0
            while (
                "Home" not in [item.name for item in service.items("links")]
                and time.monotonic() < deadline
            ):
                time.sleep(0.02)
        finally:
            watcher.stop()

        names = [item.name for item in service.items("links")]
        self.assertIn("Home", names)
        self.assertIn("PyPI", names)


class ServerStartupBookmarkTests(EnvFixtureTestCase):
    """The backend imports existing bookmarks before serving the first request."""

    def _server(self, app_dir: Path) -> JsonLinesServer:
        return JsonLinesServer(
            app_dir, in_stream=io.StringIO(""), out_stream=io.StringIO("")
        )

    def test_starting_the_server_imports_existing_bookmarks(self) -> None:
        write_profile(self.chrome_root, "Default", sync_fixture_document())
        app_dir = self.base / "app"
        server = self._server(app_dir)
        try:
            server._start_bookmarks()
        finally:
            server.dispatcher.stop_bookmarks()

        payload = json.loads((app_dir / "sites.json").read_text(encoding="utf-8"))
        names = [entry["name"] for entry in payload]
        self.assertIn("Home", names)
        self.assertIn("PyPI", names)

    def test_a_second_start_does_not_duplicate_bookmarks(self) -> None:
        write_profile(self.chrome_root, "Default", sync_fixture_document())
        app_dir = self.base / "app"
        first = self._server(app_dir)
        try:
            first._start_bookmarks()
        finally:
            first.dispatcher.stop_bookmarks()
        size_after_first = len(
            json.loads((app_dir / "sites.json").read_text(encoding="utf-8"))
        )

        second = self._server(app_dir)
        try:
            second._start_bookmarks()
        finally:
            second.dispatcher.stop_bookmarks()
        size_after_second = len(
            json.loads((app_dir / "sites.json").read_text(encoding="utf-8"))
        )
        self.assertEqual(size_after_first, size_after_second)


if __name__ == "__main__":
    unittest.main()
