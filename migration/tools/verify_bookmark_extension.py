"""Phase 18 end-to-end check: loopback bookmark bridge + simulated extension.

Runs the real Python backend over stdio with a fake Chrome profile (never the
developer's real browser data), then plays the browser extension over HTTP:

  1. startup import, delete-with-removeFromBrowser queues a command;
  2. /ping becomes "connected", /commands returns the removal, /ack clears it;
  3. reverse rename event updates the resource name + emits one bookmarks event;
  4. reverse removed event deletes the resource and prunes the seen ledger, so
     re-bookmarking the same URL imports it again;
  5. a newly bookmarked site is picked up by the file watcher;
  6. the bridge closes when the backend exits, and the browser file is never
     written by the backend.

    D:\\miniconda3\\python.exe migration/tools/verify_bookmark_extension.py
"""

from __future__ import annotations

import json
import os
import shutil
import queue
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_MAIN = REPO_ROOT / "backend" / "main.py"
PYTHON = Path(r"D:\miniconda3\python.exe")
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

report: dict[str, object] = {"probes": {}}


def record(name: str, ok: bool, detail: str, **extra) -> None:
    report["probes"][name] = {"ok": bool(ok), "detail": detail, **extra}
    print(("PASS " if ok else "FAIL ") + name + " — " + detail)


def url_node(name: str, url: str) -> dict:
    return {"type": "url", "name": name, "url": url}


def bookmarks_document(extra: list[dict] | None = None) -> dict:
    children = [
        url_node("Home", "https://home.example/"),
        url_node("Docs", "https://docs.example/"),
    ]
    if extra:
        children.extend(extra)
    return {
        "roots": {
            "bookmark_bar": {
                "type": "folder",
                "name": "Bookmarks bar",
                "children": children,
            }
        }
    }


class Backend:
    """Tiny JSON-Lines client around a real backend subprocess."""

    def __init__(self, data_dir: Path, browser_root: Path) -> None:
        env = dict(os.environ)
        env["RH_BROWSER_DATA_DIRS"] = str(browser_root)
        self._process = subprocess.Popen(
            [str(PYTHON), str(BACKEND_MAIN), str(data_dir)],
            cwd=str(REPO_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        self._next_id = 1
        self._responses: dict[int, dict] = {}
        self._events: list[dict] = []
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._stdout_thread = threading.Thread(
            target=self._read_stdout, name="backend-stdout", daemon=True
        )
        self._stdout_thread.start()

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        for raw in self._process.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                frame = json.loads(line)
            except json.JSONDecodeError:
                continue
            with self._condition:
                if "id" in frame:
                    self._responses[int(frame["id"])] = frame
                else:
                    self._events.append(frame)
                self._condition.notify_all()

    def call(self, method: str, params: dict | None = None, timeout: float = 10.0) -> dict:
        request_id = self._next_id
        self._next_id += 1
        frame = {"id": request_id, "method": method, "params": params or {}}
        assert self._process.stdin is not None
        self._process.stdin.write(
            (json.dumps(frame, ensure_ascii=False) + "\n").encode("utf-8")
        )
        self._process.stdin.flush()
        deadline = time.time() + timeout
        with self._condition:
            while request_id not in self._responses:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError(f"{method} timed out")
                self._condition.wait(remaining)
            response = self._responses.pop(request_id)
        if not response.get("ok"):
            raise RuntimeError(f"{method} failed: {response.get('error')}")
        return response["result"]

    def drain_events(self) -> None:
        with self._condition:
            self._events.clear()

    def wait_event(
        self,
        name: str,
        timeout: float = 10.0,
        predicate=None,
    ) -> dict | None:
        deadline = time.time() + timeout
        with self._condition:
            while True:
                for index, event in enumerate(self._events):
                    if event.get("event") == name and (
                        predicate is None or predicate(event)
                    ):
                        return self._events.pop(index)
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)

    def close(self) -> int:
        try:
            self.call("app.shutdown", timeout=5.0)
        except (TimeoutError, RuntimeError, OSError):
            pass
        assert self._process.stdin is not None
        try:
            self._process.stdin.close()
        except OSError:
            pass
        try:
            return self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
            return self._process.wait(timeout=5)


def http_json(
    base: str, path: str, payload: dict | None = None, timeout: float = 5.0
) -> tuple[int, dict]:
    url = base + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")
        try:
            return error.code, json.loads(body)
        except json.JSONDecodeError:
            return error.code, {}


def wait_until(predicate, timeout: float = 10.0, interval: float = 0.15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except Exception:  # noqa: BLE001 - probe loop
            pass
        time.sleep(interval)
    return False


def find_resource(backend: Backend, name: str) -> dict | None:
    result = backend.call("resources.list", {"mode": "links"})
    for item in result["items"]:
        if item["name"] == name:
            return item
    return None


def main() -> int:
    if not BACKEND_MAIN.exists():
        print(f"backend not found: {BACKEND_MAIN}")
        return 1
    work = Path(tempfile.mkdtemp(prefix="rh-extension-qa-"))
    data_dir = work / "data"
    browser_root = work / "browser" / "User Data"
    profile = browser_root / "Default"
    profile.mkdir(parents=True)
    bookmark_file = profile / "Bookmarks"
    bookmark_file.write_text(
        json.dumps(bookmarks_document(), ensure_ascii=False), encoding="utf-8"
    )
    original_bytes = bookmark_file.read_bytes()
    backend: Backend | None = None
    base: str | None = None
    try:
        backend = Backend(data_dir, browser_root)
        backend.call("app.hello")
        # The backend imports existing bookmarks before serving the first
        # request, so the first resources.list already contains them.
        listed = backend.call("resources.list", {"mode": "links"})
        names = [item["name"] for item in listed["items"]]
        imported = backend.call("bookmarks.sync")
        backend.drain_events()
        record(
            "startup_import",
            "Home" in names
            and "Docs" in names
            and imported["added"] == 0
            and imported["total"] == 2,
            f"names={names} sync_added={imported['added']}",
        )
        home = find_resource(backend, "Home")
        record("imported_resource_found", home is not None, f"home={bool(home)}")
        if home is None:
            raise SystemExit(2)

        # The browser file must not be written by the backend.
        record(
            "browser_file_read_only",
            bookmark_file.read_bytes() == original_bytes,
            "Bookmarks bytes unchanged after import",
        )

        # Tool-side delete with removeFromBrowser queues a command (extension
        # has not connected yet).
        deleted = backend.call(
            "resources.delete",
            {
                "mode": "links",
                "id": home["id"],
                "removeFromBrowser": True,
            },
        )
        record(
            "delete_queues_browser_command",
            deleted.get("deleted") is True
            and deleted.get("browserQueued") is True
            and deleted.get("extensionConnected") is False,
            f"response={deleted}",
        )
        status = backend.call("bookmarks.extensionStatus")
        record(
            "extension_status_before_connect",
            status.get("connected") is False
            and status.get("pendingCommands") == 1
            and isinstance(status.get("port"), int),
            f"status={status}",
        )
        port = status.get("port")
        if not isinstance(port, int):
            raise SystemExit(3)
        base = f"http://127.0.0.1:{port}"

        # Simulated extension: ping marks it connected, /commands returns the
        # queued removal, /ack clears it.
        http_code, ping = http_json(base, "/ping")
        record(
            "extension_ping",
            http_code == 200 and ping.get("app") == "resource-hub",
            f"http={http_code} body={ping}",
        )
        status = backend.call("bookmarks.extensionStatus")
        record(
            "extension_connected",
            status.get("connected") is True and status.get("pendingCommands") == 1,
            f"status={status}",
        )
        http_code, commands = http_json(base, "/commands")
        queued = commands.get("commands") or []
        record(
            "commands_returned",
            http_code == 200
            and len(queued) == 1
            and queued[0].get("op") == "remove"
            and queued[0].get("urls") == ["https://home.example/"],
            f"http={http_code} commands={queued}",
        )
        if queued:
            http_code, ack = http_json(
                base,
                "/ack",
                {"results": [{"id": queued[0]["id"], "removed": 1, "failed": 0}]},
            )
        else:
            http_code, ack = 0, {}
        record(
            "ack_clears_command",
            http_code == 200
            and ack.get("ok") is True
            and backend.call("bookmarks.extensionStatus").get("pendingCommands") == 0,
            f"http={http_code} ack={ack}",
        )

        # Reverse rename: browser extension reports a changed bookmark title.
        http_code, events = http_json(
            base,
            "/events",
            {
                "events": [
                    {"type": "changed", "url": "https://docs.example/", "title": "Docs Renamed"}
                ]
            },
        )
        renamed_frame = backend.wait_event(
            "bookmarks",
            timeout=5.0,
            predicate=lambda event: int(
                (event.get("payload") or {}).get("renamed") or 0
            )
            > 0,
        )
        renamed_item = find_resource(backend, "Docs Renamed")
        record(
            "reverse_rename",
            http_code == 200
            and events.get("renamed") == 1
            and renamed_frame is not None
            and renamed_flag(renamed_frame) == 1
            and renamed_item is not None,
            f"http={http_code} events={events} resource={bool(renamed_item)}",
        )

        # Reverse remove: unbookmarked in the browser -> removed here, seen
        # ledger pruned so a later re-bookmark imports again.
        http_code, events = http_json(
            base,
            "/events",
            {"events": [{"type": "removed", "url": "https://docs.example/"}]},
        )
        deleted_frame = backend.wait_event(
            "bookmarks",
            timeout=5.0,
            predicate=lambda event: int(
                (event.get("payload") or {}).get("deleted") or 0
            )
            > 0,
        )
        record(
            "reverse_remove",
            http_code == 200
            and events.get("deleted") == 1
            and deleted_frame is not None
            and deleted_flag(deleted_frame) == 1
            and find_resource(backend, "Docs Renamed") is None,
            f"http={http_code} events={events}",
        )

        # Re-bookmark the same URL: the seen ledger was pruned on removal, so the
        # watcher imports it again.
        document = bookmarks_document(
            extra=[url_node("Docs", "https://docs.example/")]
        )
        bookmark_file.write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8"
        )
        reimported = wait_until(
            lambda: find_resource(backend, "Docs") is not None, timeout=12.0
        )
        record(
            "rebookmark_imports_again",
            reimported,
            f"resource={bool(find_resource(backend, 'Docs'))}",
        )

        # A brand-new bookmark is picked up by the watcher.
        document["roots"]["bookmark_bar"]["children"].append(
            url_node("Watched", "https://watched.example/")
        )
        bookmark_file.write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8"
        )
        watched = wait_until(
            lambda: find_resource(backend, "Watched") is not None, timeout=12.0
        )
        record("watcher_imports_new_bookmark", watched, "Watched imported")

        exit_code = backend.close()
        backend = None  # type: ignore[assignment]
        record("backend_clean_exit", exit_code == 0, f"exit={exit_code}")
        bridge_closed = wait_until(
            lambda: not ping_ok(base) if base else True, timeout=5.0
        )
        record("bridge_closed_with_backend", bridge_closed, f"port={port}")
    finally:
        if backend is not None:
            backend.close()
        time.sleep(0.5)
        shutil.rmtree(work, ignore_errors=True)

    failed = [name for name, probe in report["probes"].items() if not probe["ok"]]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n{len(report['probes']) - len(failed)}/{len(report['probes'])} checks passed")
    return 0 if not failed else 1


def renamed_flag(frame: dict) -> int:
    payload = frame.get("payload") or {}
    return int(payload.get("renamed") or 0)


def deleted_flag(frame: dict) -> int:
    payload = frame.get("payload") or {}
    return int(payload.get("deleted") or 0)


def ping_ok(base: str) -> bool:
    try:
        code, body = http_json(base, "/ping", timeout=1.0)
        return code == 200 and body.get("app") == "resource-hub"
    except Exception:  # noqa: BLE001 - closed port
        return False


if __name__ == "__main__":
    raise SystemExit(main())
