"""Phase 19 real-device check: Explorer folder context menu.

Verifies the HKCU menu registration and the `--add-folder` path (both with the
app running and closed), then checks that turning the setting off removes the
registry entry again. The user's folders.json / settings.json are backed up and
restored byte-for-byte before the script ends.

    D:\\miniconda3\\python.exe migration/tools/verify_context_menu.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STABLE = REPO_ROOT / "release" / "ResourceHub-Desktop-20261017-1835"
EXE = STABLE / "resource_hub.exe"
MENU_KEY = r"Software\Classes\Directory\shell\ResourceHubAddFolder"
MENU_BACKGROUND_KEY = (
    r"Software\Classes\Directory\Background\shell\ResourceHubAddFolder"
)
MENU_LABEL = "添加到抽屉"
MENU_BACKGROUND_LABEL = "添加当前文件夹到抽屉"
WINDOW_CLASS = "FLUTTER_RUNNER_WIN32_WINDOW"
report: dict[str, object] = {"probes": {}}


def record(name: str, ok: bool, detail: str, **extra) -> None:
    report["probes"][name] = {"ok": bool(ok), "detail": detail, **extra}
    print(("PASS " if ok else "FAIL ") + name + " — " + detail)


def wait_until(predicate, timeout: float = 20.0, interval: float = 0.25) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(interval)
    return False


def read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _read_entry(key_path: str) -> dict[str, str] | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            label = winreg.QueryValueEx(key, "")[0]
            icon = winreg.QueryValueEx(key, "Icon")[0]
    except OSError:
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path + r"\command"
        ) as command_key:
            command = winreg.QueryValueEx(command_key, "")[0]
    except OSError:
        command = ""
    return {"label": label, "icon": icon, "command": command}


def read_menu_values() -> dict[str, str] | None:
    return _read_entry(MENU_KEY)


def read_background_values() -> dict[str, str] | None:
    return _read_entry(MENU_BACKGROUND_KEY)


def menu_installed() -> bool:
    return read_menu_values() is not None


def app_processes() -> int:
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq resource_hub.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return sum(
        1 for line in result.stdout.splitlines() if line.lower().startswith('"resource_hub.exe"')
    )


def window_visible() -> bool:
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(WINDOW_CLASS, None)
    return bool(hwnd) and bool(user32.IsWindowVisible(hwnd))


def kill_app(wait: bool = True) -> None:
    subprocess.run(
        ["taskkill", "/IM", "resource_hub.exe", "/F"],
        capture_output=True,
        timeout=20,
    )
    if wait:
        wait_until(lambda: app_processes() == 0, timeout=10.0)


def start_app(*arguments: str) -> subprocess.Popen:
    return subprocess.Popen(
        [str(EXE), *arguments],
        cwd=str(STABLE),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def folder_entries(path: Path) -> list[dict]:
    payload = read_json(path / "folders.json") or []
    return payload if isinstance(payload, list) else []


def find_folder(path: Path, target: Path) -> dict | None:
    needle = str(target).rstrip("\\/").lower()
    for entry in folder_entries(path):
        if str(entry.get("path", "")).rstrip("\\/").lower() == needle:
            return entry
    return None


def run_add(exe_dir: Path, target: Path, *, wait_seconds: float = 2.0) -> None:
    """Starts the context-menu command without waiting for the app to exit."""
    subprocess.Popen(
        [str(EXE), "--add-folder", str(target)],
        cwd=str(exe_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(wait_seconds)


def main() -> int:
    if not EXE.exists():
        print(f"missing release exe: {EXE}")
        return 1
    work = Path(tempfile.mkdtemp(prefix="rh-ctx-qa-"))
    folders_json = STABLE / "folders.json"
    settings_json = STABLE / "settings.json"
    folders_backup = folders_json.read_bytes() if folders_json.exists() else None
    settings_backup = settings_json.read_bytes() if settings_json.exists() else None
    first = work / "第一个 测试文件夹"
    second = work / "第二个 测试文件夹"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    try:
        kill_app()
        # 1. A normal launch registers the HKCU entry.
        start_app()
        registered = wait_until(menu_installed, timeout=25.0)
        values = read_menu_values() or {}
        background = read_background_values() or {}
        record(
            "context_menu_registered_on_start",
            registered
            and values.get("label") == MENU_LABEL
            and str(EXE) in values.get("icon", "")
            and str(EXE) in values.get("command", "")
            and '--add-folder "%1"' in values.get("command", "")
            and background.get("label") == MENU_BACKGROUND_LABEL
            and str(EXE) in background.get("icon", "")
            and '--add-folder "%V"' in background.get("command", ""),
            f"folder={values} background={background}",
        )
        record(
            "window_visible_after_launch",
            wait_until(window_visible, timeout=20.0),
            "FLUTTER_RUNNER_WIN32_WINDOW visible",
        )

        # 2. Context-menu invocation while the app is running: the second
        #    instance must forward the path and leave exactly one app process.
        run_add(STABLE, first)
        added = wait_until(
            lambda: find_folder(STABLE, first) is not None, timeout=20.0
        )
        entry = find_folder(STABLE, first) or {}
        record(
            "add_folder_while_running",
            added
            and entry.get("name") == first.name
            and entry.get("category") in ("__uncategorized__", "未分类"),
            f"entry={entry}",
        )
        record(
            "no_second_app_process",
            app_processes() == 1,
            f"resource_hub.exe count={app_processes()}",
        )
        record(
            "window_visible_after_add",
            wait_until(window_visible, timeout=10.0),
            "window still visible after the context-menu add",
        )

        # 3. Duplicate invocation must not create another row.
        run_add(STABLE, first)
        time.sleep(1.5)
        duplicates = [
            item
            for item in folder_entries(STABLE)
            if str(item.get("path", "")).rstrip("\\/").lower()
            == str(first).rstrip("\\/").lower()
        ]
        record(
            "duplicate_add_is_ignored",
            len(duplicates) == 1,
            f"matching rows={len(duplicates)}",
        )

        # 4. Invocation while the app is closed must start it and add the path.
        kill_app()
        run_add(STABLE, second)
        started = wait_until(
            lambda: app_processes() >= 1
            and find_folder(STABLE, second) is not None,
            timeout=40.0,
        )
        record(
            "add_folder_when_closed",
            started,
            f"processes={app_processes()} entry={find_folder(STABLE, second)}",
        )

        # 5. Turning the setting off removes the HKCU entry (and back on
        #    restores it) — the runner owns the registry, the backend persists
        #    the flag.
        payload = read_json(settings_json) or {}
        if not isinstance(payload, dict):
            payload = {}
        payload["shellContextMenuEnabled"] = False
        kill_app()
        write_json(settings_json, payload)
        start_app()
        removed = wait_until(
            lambda: not menu_installed()
            and read_background_values() is None,
            timeout=25.0,
        )
        record(
            "toggle_off_removes_menu",
            removed,
            f"installed={menu_installed()} background="
            f"{read_background_values() is not None}",
        )

        payload["shellContextMenuEnabled"] = True
        kill_app()
        write_json(settings_json, payload)
        start_app()
        restored = wait_until(
            lambda: menu_installed() and read_background_values() is not None,
            timeout=25.0,
        )
        record(
            "toggle_on_restores_menu",
            restored,
            f"installed={menu_installed()} background="
            f"{read_background_values() is not None}",
        )
    finally:
        kill_app()
        if folders_backup is not None:
            folders_json.write_bytes(folders_backup)
        elif folders_json.exists():
            folders_json.unlink()
        if settings_backup is not None:
            settings_json.write_bytes(settings_backup)
        shutil.rmtree(work, ignore_errors=True)
        # Leave the app running in its normal visible state for the user.
        start_app()
        wait_until(window_visible, timeout=25.0)
        record(
            "user_data_restored",
            (folders_backup is None or folders_json.read_bytes() == folders_backup)
            and (
                settings_backup is None
                or settings_json.read_bytes() == settings_backup
            ),
            "folders.json / settings.json restored",
        )

    failed = [name for name, probe in report["probes"].items() if not probe["ok"]]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n{len(report['probes']) - len(failed)}/{len(report['probes'])} checks passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
