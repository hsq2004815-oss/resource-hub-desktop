"""Tests for Phase 34: preset openers and how a path is launched with one."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from resource_hub_core.launcher import open_path
from resource_hub_core.models import Folder
from resource_hub_core.openers import (
    KIND_EDITOR,
    KIND_TERMINAL,
    Opener,
    find_opener,
    installed_openers,
)


class OpenerListTests(unittest.TestCase):
    def test_the_system_default_is_always_offered(self) -> None:
        openers = {opener.id: opener for opener in installed_openers()}
        self.assertIn("system", openers)
        self.assertTrue(openers["system"].available)
        # The launcher treats an empty command as "system default".
        self.assertEqual(openers["system"].command, "")

    def test_presets_are_stable_across_machines(self) -> None:
        ids = [opener.id for opener in installed_openers()]
        self.assertEqual(
            ids, ["system", "vscode", "wt", "powershell", "cmd"]
        )

    def test_an_unavailable_preset_never_matches(self) -> None:
        with mock.patch(
            "resource_hub_core.openers.installed_openers",
            return_value=[Opener("vscode", "Code", "", KIND_EDITOR)],
        ):
            self.assertIsNone(find_opener("vscode"))

    def test_unknown_ids_are_not_openers(self) -> None:
        self.assertIsNone(find_opener(""))
        self.assertIsNone(find_opener("notepad"))


class OpenPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.folder = self.dir / "proj"
        self.folder.mkdir()
        self.file = self.dir / "note.md"
        self.file.write_text("x", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, target: Path, opener: Opener | None, opener_id: str):
        with (
            mock.patch(
                "resource_hub_core.launcher.find_opener", return_value=opener
            ),
            mock.patch("resource_hub_core.launcher._popen") as popen,
            mock.patch("resource_hub_core.launcher._startfile") as start,
        ):
            open_path(str(target), opener_id)
        return popen, start

    def test_an_unknown_opener_falls_back_to_the_system(self) -> None:
        popen, start = self._run(self.folder, None, "nope")
        start.assert_called_once_with(str(self.folder))
        popen.assert_not_called()

    def test_an_editor_opens_the_target_itself(self) -> None:
        opener = Opener("vscode", "Code", r"E:\Code.exe", KIND_EDITOR)
        popen, start = self._run(self.file, opener, "vscode")
        args, kwargs = popen.call_args
        self.assertEqual(args[0], [r"E:\Code.exe", str(self.file)])
        self.assertNotIn("ELECTRON_RUN_AS_NODE", kwargs["env"])
        start.assert_not_called()

    def test_a_terminal_opens_in_the_folder(self) -> None:
        opener = Opener("wt", "Windows Terminal", r"C:\wt.exe", KIND_TERMINAL)
        popen, _start = self._run(self.folder, opener, "wt")
        args, _kwargs = popen.call_args
        self.assertEqual(args[0], [r"C:\wt.exe", "-d", str(self.folder)])

    def test_a_terminal_on_a_file_uses_its_parent(self) -> None:
        opener = Opener("wt", "Windows Terminal", r"C:\wt.exe", KIND_TERMINAL)
        popen, _start = self._run(self.file, opener, "wt")
        args, _kwargs = popen.call_args
        self.assertEqual(args[0], [r"C:\wt.exe", "-d", str(self.dir)])

    def test_a_shell_starts_in_the_directory_without_typing_cd(self) -> None:
        opener = Opener("cmd", "Command Prompt", r"C:\cmd.exe", KIND_TERMINAL)
        popen, _start = self._run(self.folder, opener, "cmd")
        args, kwargs = popen.call_args
        self.assertEqual(args[0], [r"C:\cmd.exe", "/K"])
        self.assertEqual(kwargs["cwd"], str(self.folder))

    def test_a_missing_path_raises_before_launching(self) -> None:
        with mock.patch("resource_hub_core.launcher._popen") as popen:
            with self.assertRaises(Exception):
                open_path(str(self.dir / "gone"), "")
        popen.assert_not_called()


class FolderOpenWithModelTests(unittest.TestCase):
    def test_open_with_round_trips(self) -> None:
        folder = Folder.normalize(
            {"name": "p", "path": r"D:\p", "kind": "folder", "openWith": " VS Code "}
        )
        self.assertEqual(folder.open_with, "vs code")
        self.assertEqual(folder.to_json()["openWith"], "vs code")

    def test_absent_open_with_stays_out_of_the_file(self) -> None:
        folder = Folder.normalize({"name": "p", "path": r"D:\p", "kind": "folder"})
        self.assertEqual(folder.open_with, "")
        self.assertNotIn("openWith", folder.to_json())


if __name__ == "__main__":
    unittest.main()
