"""Phase 22 end-to-end check: AI category suggestions over a mock endpoint.

Runs the real Python backend over stdio with a temporary data directory, points
`aiBaseUrl` at a local OpenAI-compatible mock server, stores a fake key through
DPAPI, and verifies the full suggestion contract — no real network, no real key,
and no writes until the suggestions are applied explicitly.

    D:\\miniconda3\\python.exe migration/tools/verify_ai_suggest.py
"""

from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path(r"D:\miniconda3\python.exe")
if not PYTHON.exists():
    PYTHON = Path(sys.executable)
BACKEND_MAIN = REPO_ROOT / "backend" / "main.py"
report: dict[str, object] = {"probes": {}}
mock_state: dict[str, object] = {}


def record(name: str, ok: bool, detail: str, **extra) -> None:
    report["probes"][name] = {"ok": bool(ok), "detail": detail, **extra}
    print(("PASS " if ok else "FAIL ") + name + " — " + detail)


class MockAiHandler(BaseHTTPRequestHandler):
    server_version = "MockAI/1.0"

    def log_message(self, *_args) -> None:  # silence the test output
        return

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        mock_state["path"] = self.path
        mock_state["authorization"] = self.headers.get("Authorization", "")
        try:
            body = json.loads(raw.decode("utf-8"))
            messages = body.get("messages", [])
            user_content = messages[-1].get("content", "")
            items = json.loads(user_content)
        except (UnicodeDecodeError, json.JSONDecodeError, IndexError):
            items = []
        mock_state["model"] = body.get("model") if isinstance(body, dict) else None
        mock_state["body"] = raw.decode("utf-8", "replace")
        reply = []
        for item in items:
            kind = item.get("kind", "link")
            reply.append(
                {
                    "id": item.get("id", ""),
                    "category": "工具" if kind == "link" else "资料",
                    "reason": "mock category based on " + kind,
                }
            )
        # One bogus row proves the dispatcher validates ids instead of trusting
        # the model blindly.
        reply.append({"id": "bogus-id", "category": "工具", "reason": "nope"})
        content = "```json\n" + json.dumps(reply, ensure_ascii=False) + "\n```"
        payload = json.dumps(
            {"choices": [{"message": {"content": content}}]},
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class Backend:
    def __init__(self, data_dir: Path) -> None:
        env = dict(os.environ)
        env["RH_BROWSER_DATA_DIRS"] = ""
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
        self._condition = threading.Condition()
        self._thread = threading.Thread(
            target=self._read, name="backend-stdout", daemon=True
        )
        self._thread.start()

    def _read(self) -> None:
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
                    self._condition.notify_all()

    def raw(self, method: str, params: dict | None = None, timeout: float = 90.0) -> dict:
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
            return self._responses.pop(request_id)

    def call(self, method: str, params: dict | None = None) -> dict:
        frame = self.raw(method, params)
        if not frame.get("ok"):
            error = frame.get("error") or {}
            raise RuntimeError(f"{method} failed: {error}")
        return frame.get("result") or {}

    def close(self) -> int:
        try:
            self.call("app.shutdown")
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


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="rh-ai-qa-"))
    data_dir = work / "data"
    folders = [work / "Logos", work / "Taxes"]
    for folder in folders:
        folder.mkdir(parents=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockAiHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    backend: Backend | None = None
    try:
        backend = Backend(data_dir)
        hello = backend.call("app.hello")
        record(
            "hello_lists_ai_methods",
            {"ai.status", "ai.setKey", "ai.suggestCategories"}
            <= set(hello.get("methods", [])),
            f"ai methods in hello: {sorted(m for m in hello.get('methods', []) if m.startswith('ai.'))}",
        )
        status = backend.call("ai.status")
        record(
            "defaults_are_off",
            status.get("enabled") is False
            and status.get("configured") is False
            and status.get("baseUrl") == "https://api.deepseek.com"
            and status.get("model") == "deepseek-chat",
            f"status={status}",
        )
        code = backend.raw("ai.suggestCategories").get("error", {}).get("code")
        record("disabled_error", code == "ai_disabled", f"code={code}")

        backend.call(
            "settings.set",
            {
                "settings": {
                    "aiEnabled": True,
                    "aiBaseUrl": base_url,
                    "aiModel": "mock-model",
                }
            },
        )
        status = backend.call("ai.status")
        record(
            "settings_persist",
            status.get("enabled") is True
            and status.get("baseUrl") == base_url
            and status.get("model") == "mock-model"
            and status.get("configured") is False,
            f"status={status}",
        )
        code = backend.raw("ai.suggestCategories").get("error", {}).get("code")
        record("not_configured_error", code == "ai_not_configured", f"code={code}")

        key = "sk-test-phase22"
        record(
            "set_key",
            backend.call("ai.setKey", {"apiKey": key}).get("configured") is True,
            "fake key stored through DPAPI",
        )
        key_file = data_dir / ".resourcehub-ai-key"
        key_bytes = key_file.read_bytes() if key_file.exists() else b""
        record(
            "key_file_encrypted",
            key_file.exists() and key.encode() not in key_bytes,
            f"file={key_file.name} size={len(key_bytes)} plaintext_absent={key.encode() not in key_bytes}",
        )

        # Prepare uncategorized links + folders.
        backend.call(
            "resources.add",
            {"mode": "links", "name": "PyPI", "target": "https://pypi.org/"},
        )
        backend.call(
            "resources.add",
            {"mode": "links", "name": "Figma", "target": "https://figma.com/"},
        )
        for folder in folders:
            backend.call(
                "resources.add",
                {"mode": "folders", "name": folder.name, "target": str(folder)},
            )

        result = backend.call("ai.suggestCategories")
        suggestions = result.get("suggestions") or []
        modes = sorted(s.get("mode") for s in suggestions)
        record(
            "suggestions_returned",
            len(suggestions) == 4
            and modes == ["folders", "folders", "links", "links"]
            and all(s.get("suggestedCategory") for s in suggestions)
            and all(s.get("id") != "bogus-id" for s in suggestions),
            f"count={len(suggestions)} modes={modes}",
        )
        record(
            "request_count_and_model",
            result.get("requestCount") == 4 and result.get("model") == "mock-model",
            f"requestCount={result.get('requestCount')} model={result.get('model')}",
        )
        auth = str(mock_state.get("authorization", ""))
        payload = str(mock_state.get("body", ""))
        record(
            "request_is_authenticated",
            auth == f"Bearer {key}",
            f"Authorization header={auth[:20]}…",
        )
        record(
            "no_local_paths_in_prompt",
            str(work) not in payload
            and "C:\\\\" not in payload
            and "Logos" in payload
            and "Figma" in payload,
            "mock prompt contains names/urls but not the full folder paths",
        )

        # The user (UI) applies suggestions explicitly.
        applied = 0
        for suggestion in suggestions:
            backend.call(
                "resources.update",
                {
                    "mode": suggestion["mode"],
                    "id": suggestion["id"],
                    "name": suggestion["name"],
                    "target": suggestion["target"],
                    "category": suggestion["suggestedCategory"],
                    "note": suggestion.get("note", ""),
                },
            )
            applied += 1
        links = backend.call("resources.list", {"mode": "links"}).get("items", [])
        folders_list = backend.call("resources.list", {"mode": "folders"}).get("items", [])
        by_name = {item["name"]: item for item in links + folders_list}
        record(
            "applying_suggestions_updates_categories",
            applied == 4
            and by_name.get("PyPI", {}).get("category") == "工具"
            and by_name.get("Logos", {}).get("category") == "资料",
            f"applied={applied} PyPI={by_name.get('PyPI', {}).get('category')} "
            f"Logos={by_name.get('Logos', {}).get('category')}",
        )

        # Clearing the key disables suggestions again.
        backend.call("ai.setKey", {"apiKey": ""})
        code = backend.raw("ai.suggestCategories").get("error", {}).get("code")
        record(
            "clearing_key_requires_reconfiguration",
            code == "ai_not_configured" and not key_file.exists(),
            f"code={code} key_file_exists={key_file.exists()}",
        )

        # Network failure maps to ai_request_failed with a safe detail.
        backend.call("ai.setKey", {"apiKey": key})
        # Make one item uncategorized again so the dispatcher actually issues a
        # request (otherwise it would short-circuit with zero items and no HTTP).
        first = suggestions[0]
        backend.call(
            "resources.update",
            {
                "mode": first["mode"],
                "id": first["id"],
                "name": first["name"],
                "target": first["target"],
                "category": "",
                "note": first.get("note", ""),
            },
        )
        dead_port = free_port()
        backend.call(
            "settings.set",
            {
                "settings": {
                    "aiEnabled": True,
                    "aiBaseUrl": f"http://127.0.0.1:{dead_port}",
                    "aiModel": "mock-model",
                }
            },
        )
        error = backend.raw("ai.suggestCategories").get("error") or {}
        record(
            "network_failure_is_reported",
            error.get("code") == "ai_request_failed"
            and key not in json.dumps(error),
            f"code={error.get('code')} detail={str(error.get('detail'))[:80]}",
        )
    finally:
        if backend is not None:
            backend.close()
        server.shutdown()
        server.server_close()
        import shutil

        time.sleep(0.3)
        shutil.rmtree(work, ignore_errors=True)

    failed = [name for name, probe in report["probes"].items() if not probe["ok"]]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n{len(report['probes']) - len(failed)}/{len(report['probes'])} checks passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
