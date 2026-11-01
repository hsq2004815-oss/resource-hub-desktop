"""Tests for Phase 22: the AI key store, the AI client and the protocol surface.

No test touches the network: :class:`AiClient` is given a fake ``opener`` and the
protocol tests patch ``resource_hub_core.protocol.AiClient``.
"""

from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from typing import Any
from unittest import mock

from resource_hub_core.ai import (
    AI_KEY_FILENAME,
    AiClient,
    AiError,
    AiItem,
    AiKeyStore,
    AiKeyStoreError,
    _payload_item,
    _system_prompt,
)
from resource_hub_core.bookmarks import BROWSER_DATA_DIRS_ENV
from resource_hub_core.models import UNCATEGORIZED
from resource_hub_core.protocol import (
    AI_SUGGESTION_LIMIT_DEFAULT,
    JsonLinesServer,
    ProtocolError,
)

WINDOWS_ONLY = unittest.skipUnless(
    os.name == "nt", "the DPAPI key store is Windows-only"
)

TEST_KEY = "sk-test-secret-123"


def chat_reply(content: str) -> dict[str, Any]:
    """A minimal OpenAI-compatible completion response."""
    return {
        "id": "chatcmpl-1",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}}
        ],
    }


class FakeResponse:
    """Just enough of an ``http.client.HTTPResponse`` for the client."""

    def __init__(self, payload: Any = None, *, raw: bytes | None = None) -> None:
        self._body = (
            raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode()
        )
        self.closed = False

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        self.closed = True


class FakeOpener:
    """Records the request and returns a canned response (or raises)."""

    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: list[Any] = []
        self.timeouts: list[Any] = []

    def __call__(self, request: Any, timeout: Any = None) -> Any:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.error is not None:
            raise self.error
        return self.response


class AiClientTests(unittest.TestCase):
    def make_client(
        self,
        response: Any,
        *,
        base_url: str = "https://api.deepseek.com",
        timeout: Any = 60,
    ) -> tuple[AiClient, FakeOpener]:
        opener = FakeOpener(response)
        client = AiClient(
            base_url, "deepseek-chat", TEST_KEY, timeout=timeout, opener=opener
        )
        return client, opener

    # -- request shape -----------------------------------------------------
    def test_request_headers_body_and_endpoint(self) -> None:
        client, opener = self.make_client(
            FakeResponse(chat_reply("[]")), timeout=42
        )
        reply = client.suggest_categories(
            [
                AiItem(
                    "links",
                    "l1",
                    "Python Docs",
                    "https://docs.python.org/3/",
                    "link",
                )
            ],
            ["Development", "Tools"],
        )

        self.assertEqual(reply, {"model": "deepseek-chat", "suggestions": []})
        request = opener.requests[0]
        # A trailing slash on the configured base URL must not double up.
        self.assertEqual(
            request.full_url, "https://api.deepseek.com/chat/completions"
        )
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(opener.timeouts, [42])

        headers = {key.lower(): value for key, value in request.headers.items()}
        self.assertEqual(headers["authorization"], f"Bearer {TEST_KEY}")
        self.assertEqual(headers["content-type"], "application/json")

        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "deepseek-chat")
        self.assertEqual(body["temperature"], 0.1)
        self.assertEqual(body["max_tokens"], 4000)
        system = body["messages"][0]
        self.assertEqual(system["role"], "system")
        self.assertIn("Development, Tools", system["content"])
        self.assertIn('"id"', system["content"])
        self.assertIn("JSON array", system["content"])
        user = body["messages"][1]
        self.assertEqual(user["role"], "user")
        self.assertEqual(
            json.loads(user["content"]),
            [
                {
                    "id": "l1",
                    "kind": "link",
                    "name": "Python Docs",
                    "url": "https://docs.python.org/3/",
                }
            ],
        )
        # The key only ever travels in the Authorization header.
        self.assertNotIn(TEST_KEY, request.data.decode("utf-8"))

    def test_trailing_slash_is_stripped_from_the_base_url(self) -> None:
        client, opener = self.make_client(
            FakeResponse(chat_reply("[]")), base_url="https://api.example.com/v1/"
        )
        client.suggest_categories([], [])
        self.assertEqual(
            opener.requests[0].full_url,
            "https://api.example.com/v1/chat/completions",
        )

    def test_no_existing_categories_is_spelled_out(self) -> None:
        client, opener = self.make_client(FakeResponse(chat_reply("[]")))
        client.suggest_categories([], [])
        body = json.loads(opener.requests[0].data.decode("utf-8"))
        self.assertIn("(none yet)", body["messages"][0]["content"])

    def test_folder_payload_never_contains_the_full_path(self) -> None:
        client, opener = self.make_client(FakeResponse(chat_reply("[]")))
        target = str(Path("Projects") / "Design" / "Logos")
        client.suggest_categories(
            [AiItem("folders", "f1", "Logos", target, "folder")], []
        )

        raw = opener.requests[0].data.decode("utf-8")
        self.assertNotIn("Projects", raw)  # the parent of the parent
        self.assertNotIn(target, raw)
        sent = json.loads(
            json.loads(raw)["messages"][1]["content"]
        )
        self.assertEqual(
            sent,
            [{"id": "f1", "kind": "folder", "name": "Logos", "parent": "Design"}],
        )
        self.assertNotIn("target", sent[0])

    def test_dropped_file_keeps_its_kind_and_parent(self) -> None:
        client, opener = self.make_client(FakeResponse(chat_reply("[]")))
        target = str(Path("Downloads") / "report.pdf")
        client.suggest_categories(
            [AiItem("folders", "f2", "report.pdf", target, "file")], []
        )
        sent = json.loads(
            json.loads(opener.requests[0].data.decode("utf-8"))["messages"][1][
                "content"
            ]
        )
        self.assertEqual(sent[0]["kind"], "file")
        self.assertEqual(sent[0]["parent"], "Downloads")

    # -- reply parsing -----------------------------------------------------
    def test_fenced_reply_is_parsed(self) -> None:
        content = (
            "```json\n"
            '[{"id": "l1", "category": "Tools", "reason": "dev"},\n'
            ' {"id": "l2", "category": "News", "reason": "media"}]\n'
            "```"
        )
        client, _opener = self.make_client(FakeResponse(chat_reply(content)))
        reply = client.suggest_categories([], [])
        self.assertEqual(
            reply["suggestions"],
            [
                {"id": "l1", "category": "Tools", "reason": "dev"},
                {"id": "l2", "category": "News", "reason": "media"},
            ],
        )

    def test_prose_around_the_array_is_ignored(self) -> None:
        content = 'Sure! Here is the result: [{"id": "l1", "category": "X"}] Enjoy.'
        client, _opener = self.make_client(FakeResponse(chat_reply(content)))
        reply = client.suggest_categories([], [])
        self.assertEqual(reply["suggestions"], [{"id": "l1", "category": "X"}])

    def test_non_object_entries_are_dropped(self) -> None:
        content = '[1, "text", {"id": "l1", "category": "X"}]'
        client, _opener = self.make_client(FakeResponse(chat_reply(content)))
        reply = client.suggest_categories([], [])
        self.assertEqual(reply["suggestions"], [{"id": "l1", "category": "X"}])

    def test_reply_without_a_json_array_raises(self) -> None:
        client, _opener = self.make_client(
            FakeResponse(chat_reply("I cannot help with that."))
        )
        with self.assertRaises(AiError) as caught:
            client.suggest_categories([], [])
        self.assertEqual(caught.exception.code, "invalid_response")

    def test_malformed_json_in_the_reply_raises(self) -> None:
        client, _opener = self.make_client(
            FakeResponse(chat_reply('[{"id": "l1", "category": }]'))
        )
        with self.assertRaises(AiError) as caught:
            client.suggest_categories([], [])
        self.assertEqual(caught.exception.code, "invalid_response")

    def test_reply_without_choices_raises(self) -> None:
        client, _opener = self.make_client(FakeResponse({"choices": []}))
        with self.assertRaises(AiError) as caught:
            client.suggest_categories([], [])
        self.assertEqual(caught.exception.code, "invalid_response")

    def test_reply_without_message_content_raises(self) -> None:
        client, _opener = self.make_client(
            FakeResponse({"choices": [{"message": {"content": None}}]})
        )
        with self.assertRaises(AiError) as caught:
            client.suggest_categories([], [])
        self.assertEqual(caught.exception.code, "invalid_response")

    def test_non_json_http_body_raises(self) -> None:
        client, _opener = self.make_client(FakeResponse(None, raw=b"<html>nope"))
        with self.assertRaises(AiError) as caught:
            client.suggest_categories([], [])
        self.assertEqual(caught.exception.code, "invalid_response")

    def test_non_object_json_http_body_raises(self) -> None:
        client, _opener = self.make_client(FakeResponse([1, 2, 3]))
        with self.assertRaises(AiError) as caught:
            client.suggest_categories([], [])
        self.assertEqual(caught.exception.code, "invalid_response")

    # -- transport error mapping ------------------------------------------
    def test_http_error_is_mapped(self) -> None:
        error = urllib.error.HTTPError(
            "https://api.deepseek.com/chat/completions",
            401,
            "Unauthorized",
            None,
            None,
        )
        client, _opener = self.make_client(None, base_url="https://api.deepseek.com")
        client._open = FakeOpener(error=error)
        with self.assertRaises(AiError) as caught:
            client.suggest_categories([], [])
        self.assertEqual(caught.exception.code, "http_error")
        self.assertIn("401", caught.exception.detail)
        self.assertNotIn(TEST_KEY, caught.exception.detail)

    def test_network_error_is_mapped(self) -> None:
        error = urllib.error.URLError(OSError(10061, "Connection refused"))
        client, _opener = self.make_client(None)
        client._open = FakeOpener(error=error)
        with self.assertRaises(AiError) as caught:
            client.suggest_categories([], [])
        self.assertEqual(caught.exception.code, "network_error")
        self.assertNotIn(TEST_KEY, caught.exception.detail)

    def test_url_error_wrapping_a_timeout_is_mapped_to_timeout(self) -> None:
        error = urllib.error.URLError(TimeoutError("timed out"))
        client, _opener = self.make_client(None)
        client._open = FakeOpener(error=error)
        with self.assertRaises(AiError) as caught:
            client.suggest_categories([], [])
        self.assertEqual(caught.exception.code, "timeout")

    def test_raw_timeout_is_mapped_to_timeout(self) -> None:
        client, _opener = self.make_client(None)
        client._open = FakeOpener(error=TimeoutError("timed out"))
        with self.assertRaises(AiError) as caught:
            client.suggest_categories([], [])
        self.assertEqual(caught.exception.code, "timeout")


@WINDOWS_ONLY
class AiKeyStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / AI_KEY_FILENAME
        self.store = AiKeyStore(self.path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_key_file_name_is_the_documented_hidden_file(self) -> None:
        self.assertEqual(AI_KEY_FILENAME, ".resourcehub-ai-key")

    def test_missing_file_is_not_configured(self) -> None:
        self.assertFalse(self.store.has_key())
        self.assertIsNone(self.store.load())

    def test_round_trip_and_clear(self) -> None:
        self.store.save(TEST_KEY)

        self.assertTrue(self.store.has_key())
        self.assertEqual(self.store.load(), TEST_KEY)
        self.assertTrue(self.path.is_file())

        self.store.clear()
        self.assertFalse(self.store.has_key())
        self.assertIsNone(self.store.load())
        self.assertFalse(self.path.exists())

    def test_clear_is_idempotent(self) -> None:
        self.store.clear()
        self.store.clear()
        self.assertFalse(self.store.has_key())

    def test_file_is_base64_encrypted_not_plaintext(self) -> None:
        self.store.save(TEST_KEY)
        text = self.path.read_text(encoding="utf-8").strip()
        raw = self.path.read_bytes()

        self.assertNotIn(TEST_KEY, text)
        self.assertNotIn(TEST_KEY.encode("utf-8"), raw)
        # The file is base64 text, not binary.
        decoded = base64.b64decode(text.encode("ascii"), validate=True)
        self.assertGreater(len(decoded), len(TEST_KEY))

    def test_empty_key_is_rejected_and_keeps_the_previous_key(self) -> None:
        self.store.save(TEST_KEY)
        with self.assertRaises(ValueError):
            self.store.save("   ")
        self.assertEqual(self.store.load(), TEST_KEY)

    def test_corrupt_file_is_reported_as_not_configured(self) -> None:
        self.path.write_text("this is not base64 !!!", encoding="utf-8")
        self.assertTrue(self.store.has_key())  # the file exists…
        self.assertIsNone(self.store.load())  # …but cannot be decrypted

    def test_foreign_dpapi_blob_is_not_configured(self) -> None:
        self.path.write_text(
            base64.b64encode(b"not a DPAPI blob").decode("ascii"), encoding="utf-8"
        )
        self.assertTrue(self.store.has_key())
        self.assertIsNone(self.store.load())


class AiProtocolTestCase(unittest.TestCase):
    """Protocol-level helpers: one fresh server per request, shared directory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        # Never let a test read the developer's real Chrome/Edge bookmarks.
        self._browser_env = mock.patch.dict(os.environ, {BROWSER_DATA_DIRS_ENV: ""})
        self._browser_env.start()

    def tearDown(self) -> None:
        self._browser_env.stop()
        self._tmp.cleanup()

    def run_frames(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests)
        out = io.StringIO()
        server = JsonLinesServer(
            self.dir, in_stream=io.StringIO(payload), out_stream=out
        )
        server.serve_forever()
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: Any = 1,
    ) -> dict[str, Any]:
        frames = self.run_frames(
            [{"id": request_id, "method": method, "params": params or {}}]
        )
        self.assertEqual(len(frames), 1, frames)
        return frames[0]

    def enable_ai(self) -> None:
        self.call(
            "settings.set",
            {
                "settings": {
                    "aiEnabled": True,
                    "aiBaseUrl": "https://api.example.com/v1",
                    "aiModel": "deepseek-chat",
                }
            },
        )

    def configure_key(self, api_key: str = TEST_KEY) -> None:
        frame = self.call("ai.setKey", {"apiKey": api_key})
        self.assertTrue(frame["ok"], frame)
        self.assertTrue(frame["result"]["configured"])

    def add_uncategorized_link(self, name: str, url: str) -> dict[str, Any]:
        frame = self.call(
            "resources.add", {"mode": "links", "name": name, "target": url}
        )
        self.assertTrue(frame["ok"], frame)
        self.assertEqual(frame["result"]["item"]["category"], UNCATEGORIZED)
        return frame["result"]["item"]

    def add_uncategorized_folder(self, name: str) -> dict[str, Any]:
        target = self.dir / f"folder-{name}"
        target.mkdir(exist_ok=True)
        frame = self.call(
            "resources.add",
            {"mode": "folders", "name": name, "target": str(target)},
        )
        self.assertTrue(frame["ok"], frame)
        return frame["result"]["item"]

    def suggest(
        self,
        reply: dict[str, Any] | None = None,
        *,
        error: Exception | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], Any]:
        """Call ``ai.suggestCategories`` with ``AiClient`` patched out."""
        with mock.patch("resource_hub_core.protocol.AiClient") as client_cls:
            if error is not None:
                client_cls.return_value.suggest_categories.side_effect = error
            else:
                client_cls.return_value.suggest_categories.return_value = reply
            frame = self.call("ai.suggestCategories", params or {})
        return frame, client_cls


class AiStatusProtocolTests(AiProtocolTestCase):
    def test_hello_lists_the_ai_methods(self) -> None:
        methods = self.call("app.hello")["result"]["methods"]
        for method in (
            "ai.status",
            "ai.setKey",
            "ai.suggestCategories",
            "ai.undoCategorize",
        ):
            self.assertIn(method, methods)
        self.assertEqual(methods, sorted(methods))

    def test_status_defaults(self) -> None:
        result = self.call("ai.status")["result"]
        self.assertEqual(
            result,
            {
                "enabled": False,
                "configured": False,
                "baseUrl": "https://api.deepseek.com",
                "model": "deepseek-chat",
            },
        )

    @WINDOWS_ONLY
    def test_status_follows_settings_and_the_key_store(self) -> None:
        self.enable_ai()
        self.configure_key()
        result = self.call("ai.status")["result"]
        self.assertEqual(
            result,
            {
                "enabled": True,
                "configured": True,
                "baseUrl": "https://api.example.com/v1",
                "model": "deepseek-chat",
            },
        )
        # The key is stored in its own encrypted file, never in settings.json.
        settings_text = (self.dir / "settings.json").read_text(encoding="utf-8")
        self.assertNotIn(TEST_KEY, settings_text)
        self.assertNotIn("apiKey", settings_text)
        key_file = self.dir / AI_KEY_FILENAME
        self.assertTrue(key_file.is_file())
        self.assertNotIn(TEST_KEY, key_file.read_text(encoding="utf-8"))


@WINDOWS_ONLY
class AiSetKeyProtocolTests(AiProtocolTestCase):
    def test_set_key_stores_and_clears(self) -> None:
        configured = self.call("ai.setKey", {"apiKey": TEST_KEY})["result"]
        self.assertEqual(configured, {"configured": True})

        cleared = self.call("ai.setKey", {"apiKey": ""})["result"]
        self.assertEqual(cleared, {"configured": False})
        self.assertFalse((self.dir / AI_KEY_FILENAME).exists())

    def test_blank_key_clears_instead_of_storing_whitespace(self) -> None:
        self.configure_key()
        result = self.call("ai.setKey", {"apiKey": "   "})["result"]
        self.assertEqual(result, {"configured": False})
        self.assertFalse((self.dir / AI_KEY_FILENAME).exists())

    def test_set_key_requires_a_string(self) -> None:
        for params in ({}, {"apiKey": None}, {"apiKey": 42}, {"apiKey": ["x"]}):
            with self.subTest(params=params):
                frame = self.call("ai.setKey", params)
                self.assertFalse(frame["ok"])
                self.assertEqual(frame["error"]["code"], "bad_request")

    def test_set_key_failure_is_mapped_without_echoing_details(self) -> None:
        with mock.patch.object(
            AiKeyStore, "save", side_effect=AiKeyStoreError("boom sk-something")
        ):
            frame = self.call("ai.setKey", {"apiKey": TEST_KEY})
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "operation_failed")
        self.assertNotIn("sk-something", json.dumps(frame))
        self.assertNotIn(TEST_KEY, json.dumps(frame))


@WINDOWS_ONLY
class AiSuggestProtocolTests(AiProtocolTestCase):
    def test_disabled_ai_is_rejected(self) -> None:
        frame = self.call("ai.suggestCategories", {})
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "ai_disabled")

    def test_missing_key_is_rejected(self) -> None:
        self.enable_ai()
        frame = self.call("ai.suggestCategories", {})
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "ai_not_configured")

    def test_corrupt_key_file_is_treated_as_not_configured(self) -> None:
        self.enable_ai()
        self.add_uncategorized_link("A", "https://a.test")
        (self.dir / AI_KEY_FILENAME).write_text("garbage", encoding="utf-8")
        frame = self.call("ai.suggestCategories", {})
        self.assertEqual(frame["error"]["code"], "ai_not_configured")

    def test_corrupt_data_is_reported_before_any_ai_check(self) -> None:
        self.enable_ai()
        self.configure_key()
        (self.dir / "sites.json").write_text("[broken", encoding="utf-8")
        frame = self.call("ai.suggestCategories", {})
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "corrupt_data")

    def test_no_uncategorized_items_skips_the_request(self) -> None:
        self.enable_ai()
        self.configure_key()
        # First-run samples are all categorized.
        frame, client_cls = self.suggest({"model": "x", "suggestions": []})
        self.assertTrue(frame["ok"], frame)
        result = frame["result"]
        self.assertEqual(result["suggestions"], [])
        self.assertEqual(result["requestCount"], 0)
        self.assertEqual(
            result["existingCategories"], ["AI", "Development", "System"]
        )
        client_cls.assert_not_called()

    def test_valid_suggestions_are_returned_and_invalid_ones_dropped(self) -> None:
        self.enable_ai()
        self.configure_key()
        link_one = self.add_uncategorized_link("PyPI", "https://pypi.org/")
        link_two = self.add_uncategorized_link("Hacker News", "https://news.ycombinator.com/")
        folder = self.add_uncategorized_folder("Logos")
        categorized = self.call(
            "resources.add",
            {
                "mode": "links",
                "name": "Work Site",
                "target": "https://work.test",
                "category": "Work",
            },
        )["result"]["item"]

        reply = {
            "model": "deepseek-chat",
            "suggestions": [
                {"id": link_one["id"], "category": "  Development  ", "reason": " Python package index "},
                {"id": "not-in-the-batch", "category": "Ghost", "reason": "x"},
                {"id": folder["id"], "category": "Projects", "reason": "x" * 300},
                {"id": link_one["id"], "category": "Duplicate", "reason": "x"},
                {"id": link_two["id"], "category": "   ", "reason": "empty"},
                {"id": "second-empty-id", "category": "   ", "reason": "empty"},
                {"id": link_two["id"], "category": "x" * 41, "reason": "too long"},
                {"id": categorized["id"], "category": "Work", "reason": "already done"},
                {"id": 42, "category": "Numeric id", "reason": "wrong type"},
                17,
            ],
        }
        frame, client_cls = self.suggest(reply)
        self.assertTrue(frame["ok"], frame)
        result = frame["result"]

        self.assertEqual(result["model"], "deepseek-chat")
        self.assertEqual(result["requestCount"], 3)
        self.assertEqual(
            result["existingCategories"], ["AI", "Development", "System", "Work"]
        )
        self.assertEqual(
            result["suggestions"],
            [
                {
                    "mode": "links",
                    "id": link_one["id"],
                    "name": "PyPI",
                    "target": "https://pypi.org/",
                    "note": "",
                    "currentCategory": UNCATEGORIZED,
                    "suggestedCategory": "Development",
                    "reason": "Python package index",
                },
                {
                    "mode": "folders",
                    "id": folder["id"],
                    "name": "Logos",
                    "target": folder["path"],
                    "note": "",
                    "currentCategory": UNCATEGORIZED,
                    "suggestedCategory": "Projects",
                    "reason": "x" * 200,
                },
            ],
        )

        # Links are sent before folders, each capped by the limit; the batch is
        # built from the live service data and never contains categorized rows.
        # (``resources.add`` inserts at the top, so the second link comes first.)
        client_cls.assert_called_once()
        args = client_cls.call_args.args
        self.assertEqual(args[0], "https://api.example.com/v1")
        self.assertEqual(args[1], "deepseek-chat")
        self.assertEqual(args[2], TEST_KEY)
        sent_items, existing = (
            client_cls.return_value.suggest_categories.call_args.args
        )
        self.assertEqual(
            [item.id for item in sent_items],
            [link_two["id"], link_one["id"], folder["id"]],
        )
        self.assertEqual([item.kind for item in sent_items], ["link", "link", "folder"])
        self.assertEqual(sent_items[2].target, folder["path"])
        self.assertEqual(existing, ["AI", "Development", "System", "Work"])

    def test_item_categorized_during_the_request_is_dropped(self) -> None:
        out = io.StringIO()
        server = JsonLinesServer(
            self.dir, in_stream=io.StringIO(""), out_stream=out
        )
        try:
            server.dispatcher.dispatch(
                "settings.set", {"settings": {"aiEnabled": True}}
            )
            server.dispatcher.dispatch(
                "ai.setKey", {"apiKey": TEST_KEY}
            )
            item = server.dispatcher.dispatch(
                "resources.add",
                {"mode": "links", "name": "A", "target": "https://a.test"},
            )["item"]

            def categorize_now(items: Any, existing: Any) -> dict[str, Any]:
                # Simulate the user editing the row while the HTTP call runs.
                server.state.service.update(
                    "links",
                    item["id"],
                    name="A",
                    target="https://a.test",
                    category="Work",
                )
                return {
                    "suggestions": [
                        {"id": item["id"], "category": "Other", "reason": "x"}
                    ]
                }

            with mock.patch("resource_hub_core.protocol.AiClient") as client_cls:
                client_cls.return_value.suggest_categories.side_effect = (
                    categorize_now
                )
                result = server.dispatcher.dispatch(
                    "ai.suggestCategories", {}
                )
        finally:
            server._shutdown()

        self.assertEqual(result["suggestions"], [])

    def test_deleted_item_is_dropped(self) -> None:
        out = io.StringIO()
        server = JsonLinesServer(
            self.dir, in_stream=io.StringIO(""), out_stream=out
        )
        try:
            server.dispatcher.dispatch(
                "settings.set", {"settings": {"aiEnabled": True}}
            )
            server.dispatcher.dispatch("ai.setKey", {"apiKey": TEST_KEY})
            item = server.dispatcher.dispatch(
                "resources.add",
                {"mode": "links", "name": "A", "target": "https://a.test"},
            )["item"]

            def delete_now(items: Any, existing: Any) -> dict[str, Any]:
                server.state.service.delete("links", item["id"])
                return {
                    "suggestions": [
                        {"id": item["id"], "category": "Other", "reason": "x"}
                    ]
                }

            with mock.patch("resource_hub_core.protocol.AiClient") as client_cls:
                client_cls.return_value.suggest_categories.side_effect = delete_now
                result = server.dispatcher.dispatch("ai.suggestCategories", {})
        finally:
            server._shutdown()

        self.assertEqual(result["suggestions"], [])

    def test_limit_defaults_and_clamps(self) -> None:
        self.enable_ai()
        self.configure_key()
        for index in range(3):
            self.add_uncategorized_link(f"L{index}", f"https://l{index}.test")

        # default = 40 (all three items here)
        frame, _client = self.suggest({"suggestions": []})
        self.assertEqual(frame["result"]["requestCount"], 3)
        # explicit smaller limit
        frame, _client = self.suggest(
            {"suggestions": []}, params={"limit": 2}
        )
        self.assertEqual(frame["result"]["requestCount"], 2)
        # below the minimum clamps to 1
        frame, _client = self.suggest(
            {"suggestions": []}, params={"limit": 0}
        )
        self.assertEqual(frame["result"]["requestCount"], 1)
        # above the maximum clamps to the total batch (3 here)
        frame, _client = self.suggest(
            {"suggestions": []}, params={"limit": 999}
        )
        self.assertEqual(frame["result"]["requestCount"], 3)
        # junk falls back to the default
        frame, _client = self.suggest(
            {"suggestions": []}, params={"limit": "many"}
        )
        self.assertEqual(frame["result"]["requestCount"], 3)
        self.assertEqual(AI_SUGGESTION_LIMIT_DEFAULT, 40)

    def test_real_client_end_to_end_with_a_fake_transport(self) -> None:
        """The real AiClient is used; only urllib's transport is faked."""
        self.enable_ai()
        self.configure_key()
        item = self.add_uncategorized_link("PyPI", "https://pypi.org/")
        content = json.dumps(
            [
                {
                    "id": item["id"],
                    "category": "Development",
                    "reason": "package index",
                }
            ]
        )
        opener = FakeOpener(FakeResponse(chat_reply(content)))
        # ``AiClient`` looks up ``urllib.request.urlopen`` when it is created.
        with mock.patch("resource_hub_core.ai.urllib.request.urlopen", opener):
            frame = self.call("ai.suggestCategories", {"limit": 5})

        self.assertTrue(frame["ok"], frame)
        suggestions = frame["result"]["suggestions"]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["id"], item["id"])
        self.assertEqual(suggestions[0]["suggestedCategory"], "Development")
        self.assertEqual(frame["result"]["requestCount"], 1)

        request = opener.requests[0]
        self.assertEqual(
            request.full_url, "https://api.example.com/v1/chat/completions"
        )
        headers = {key.lower(): value for key, value in request.headers.items()}
        self.assertEqual(headers["authorization"], f"Bearer {TEST_KEY}")

    def test_request_failure_maps_to_ai_request_failed(self) -> None:
        self.enable_ai()
        self.configure_key()
        self.add_uncategorized_link("A", "https://a.test")

        frame, _client = self.suggest(
            error=AiError("http_error", "HTTP 401 Unauthorized")
        )
        self.assertFalse(frame["ok"])
        error = frame["error"]
        self.assertEqual(error["code"], "ai_request_failed")
        self.assertEqual(error["detail"], "HTTP 401 Unauthorized")
        self.assertNotIn("key", error)

    def test_unexpected_client_reply_is_mapped(self) -> None:
        self.enable_ai()
        self.configure_key()
        self.add_uncategorized_link("A", "https://a.test")
        frame, _client = self.suggest({"suggestions": "nope"})
        self.assertFalse(frame["ok"])
        self.assertEqual(frame["error"]["code"], "ai_request_failed")

    def test_failure_frame_never_contains_the_api_key(self) -> None:
        self.enable_ai()
        self.configure_key()
        self.add_uncategorized_link("A", "https://a.test")
        frame, _client = self.suggest(
            error=AiError("network_error", "network error: offline")
        )
        payload = json.dumps(frame, ensure_ascii=False)
        self.assertNotIn(TEST_KEY, payload)
        self.assertEqual(frame["error"]["code"], "ai_request_failed")


class AiAutoTagTests(AiProtocolTestCase):
    """Phase 29: the backend tags newly added rows on its own."""

    def _server(self) -> Any:
        out = io.StringIO()
        server = JsonLinesServer(
            self.dir, in_stream=io.StringIO(""), out_stream=out
        )
        self.addCleanup(server._shutdown)
        server.dispatcher.dispatch("settings.set", {"settings": {"aiEnabled": True}})
        server.dispatcher.dispatch("ai.setKey", {"apiKey": TEST_KEY})
        return server

    @staticmethod
    def _add(server: Any, name: str, url: str) -> dict[str, Any]:
        return server.dispatcher.dispatch(
            "resources.add", {"mode": "links", "name": name, "target": url}
        )["item"]

    @staticmethod
    def _categories(server: Any) -> dict[str, str]:
        items = server.dispatcher.dispatch("resources.list", {"mode": "links"})[
            "items"
        ]
        return {item["id"]: item["category"] for item in items}

    def _run_tag(self, server: Any, reply: dict[str, Any], ids: list[str]) -> None:
        """Drive one batch directly so no worker thread touches the network."""
        with mock.patch("resource_hub_core.protocol.AiClient") as client_cls:
            client_cls.return_value.suggest_categories.return_value = reply
            server.dispatcher._tag_batch([("links", item_id) for item_id in ids])

    def test_add_queues_only_uncategorized_items(self) -> None:
        server = self._server()
        with mock.patch.object(type(server.dispatcher), "_kick_ai") as kick:
            item = self._add(server, "A", "https://a.test")
            self.assertEqual(kick.call_args.args[0], [("links", item["id"])])
            kick.reset_mock()
            server.dispatcher.dispatch(
                "resources.add",
                {
                    "mode": "links",
                    "name": "B",
                    "target": "https://b.test",
                    "category": "Work",
                },
            )
            kick.assert_not_called()

    def test_drop_queues_the_items_it_added(self) -> None:
        server = self._server()
        target = self.dir / "dropped.txt"
        target.write_text("x", encoding="utf-8")
        with mock.patch.object(type(server.dispatcher), "_kick_ai") as kick:
            server.dispatcher.dispatch("resources.drop", {"paths": [str(target)]})
        queued = kick.call_args.args[0]
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0][0], "folders")

    def test_kick_is_a_noop_without_a_key(self) -> None:
        server = self._server()
        server.dispatcher.dispatch("ai.setKey", {"apiKey": ""})
        server.dispatcher._kick_ai([("links", "missing")])
        self.assertEqual(server.dispatcher._ai_pending, [])
        self.assertIsNone(server.dispatcher._ai_thread)

    def test_batch_writes_the_suggested_categories(self) -> None:
        server = self._server()
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            first = self._add(server, "A", "https://a.test")
            second = self._add(server, "B", "https://b.test")
        self._run_tag(
            server,
            {
                "suggestions": [
                    {"id": first["id"], "category": "Work"},
                    {"id": second["id"], "category": "AI"},
                ]
            },
            [first["id"], second["id"]],
        )
        categories = self._categories(server)
        self.assertEqual(categories[first["id"]], "Work")
        self.assertEqual(categories[second["id"]], "AI")

    def test_at_most_two_new_categories_per_run(self) -> None:
        server = self._server()
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            ids = [
                self._add(server, f"item{i}", f"https://i{i}.test")["id"]
                for i in range(3)
            ]
        self._run_tag(
            server,
            {
                "suggestions": [
                    {"id": ids[0], "category": "Alpha"},
                    {"id": ids[1], "category": "Beta"},
                    {"id": ids[2], "category": "Gamma"},
                ]
            },
            ids,
        )
        categories = self._categories(server)
        self.assertEqual(categories[ids[0]], "Alpha")
        self.assertEqual(categories[ids[1]], "Beta")
        self.assertEqual(categories[ids[2]], UNCATEGORIZED)

    def test_an_existing_category_does_not_count_against_the_cap(self) -> None:
        server = self._server()
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            server.dispatcher.dispatch(
                "resources.add",
                {
                    "mode": "links",
                    "name": "Seed",
                    "target": "https://seed.test",
                    "category": "Work",
                },
            )
            ids = [
                self._add(server, f"item{i}", f"https://j{i}.test")["id"]
                for i in range(3)
            ]
        self._run_tag(
            server,
            {
                "suggestions": [
                    {"id": ids[0], "category": "Alpha"},
                    {"id": ids[1], "category": "Beta"},
                    {"id": ids[2], "category": "Work"},
                ]
            },
            ids,
        )
        categories = self._categories(server)
        self.assertEqual(categories[ids[0]], "Alpha")
        self.assertEqual(categories[ids[1]], "Beta")
        self.assertEqual(categories[ids[2]], "Work")

    @staticmethod
    def _field(server: Any, mode: str, item_id: str, field: str) -> str:
        items = server.dispatcher.dispatch("resources.list", {"mode": mode})[
            "items"
        ]
        return next(i for i in items if i["id"] == item_id)[field]

    def test_a_generated_note_fills_a_blank_one(self) -> None:
        server = self._server()
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            item = self._add(server, "A", "https://a.test")
        self._run_tag(
            server,
            {
                "suggestions": [
                    {"id": item["id"], "category": "Work", "note": "团队代码托管"}
                ]
            },
            [item["id"]],
        )
        self.assertEqual(
            self._field(server, "links", item["id"], "note"), "团队代码托管"
        )

    def test_a_note_the_user_wrote_is_never_overwritten(self) -> None:
        server = self._server()
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            item = self._add(server, "A", "https://a.test")
        server.dispatcher.dispatch(
            "resources.update",
            {
                "mode": "links",
                "id": item["id"],
                "name": "A",
                "target": "https://a.test",
                "note": "我自己写的",
            },
        )
        self._run_tag(
            server,
            {
                "suggestions": [
                    {"id": item["id"], "category": "Work", "note": "AI 写的"}
                ]
            },
            [item["id"]],
        )
        self.assertEqual(
            self._field(server, "links", item["id"], "note"), "我自己写的"
        )

    def test_generated_note_is_clipped_to_forty_characters(self) -> None:
        server = self._server()
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            item = self._add(server, "A", "https://a.test")
        self._run_tag(
            server,
            {
                "suggestions": [
                    {
                        "id": item["id"],
                        "category": "Work",
                        "note": "很长的描述" * 20,
                    }
                ]
            },
            [item["id"]],
        )
        self.assertEqual(len(self._field(server, "links", item["id"], "note")), 40)

    def test_a_placeholder_answer_is_treated_as_no_note(self) -> None:
        server = self._server()
        for word in ("无", "N/A", "none", "-"):
            with self.subTest(word=word):
                with mock.patch.object(type(server.dispatcher), "_kick_ai"):
                    item = self._add(server, word, f"https://{word}.test")
                written = self._run_notes(
                    server,
                    {"suggestions": [{"id": item["id"], "note": word}]},
                    [item["id"]],
                )
                self.assertEqual(written, 0)
                self.assertEqual(self._field(server, "links", item["id"], "note"), "")

    def test_an_empty_note_leaves_the_field_blank(self) -> None:
        server = self._server()
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            item = self._add(server, "A", "https://a.test")
        self._run_tag(
            server,
            {
                "suggestions": [
                    {"id": item["id"], "category": "Work", "note": ""}
                ]
            },
            [item["id"]],
        )
        self.assertEqual(self._field(server, "links", item["id"], "note"), "")

    def test_undo_clears_the_generated_note(self) -> None:
        server = self._server()
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            item = self._add(server, "A", "https://a.test")
        self._run_tag(
            server,
            {
                "suggestions": [
                    {"id": item["id"], "category": "Work", "note": "AI 写的"}
                ]
            },
            [item["id"]],
        )
        server.dispatcher.dispatch("ai.undoCategorize", {})
        self.assertEqual(self._field(server, "links", item["id"], "note"), "")
        self.assertEqual(
            self._field(server, "links", item["id"], "category"), UNCATEGORIZED
        )

    def test_folder_children_are_offered_as_context(self) -> None:
        server = self._server()
        folder = self.dir / "proj"
        folder.mkdir()
        (folder / "a.txt").write_text("x", encoding="utf-8")
        (folder / "b.txt").write_text("x", encoding="utf-8")
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            added = server.dispatcher.dispatch(
                "resources.add",
                {"mode": "folders", "name": "proj", "target": str(folder)},
            )["item"]
        with mock.patch("resource_hub_core.protocol.AiClient") as client_cls:
            client_cls.return_value.suggest_categories.return_value = {
                "suggestions": []
            }
            server.dispatcher._tag_batch([("folders", added["id"])])
        call = client_cls.return_value.suggest_categories.call_args
        self.assertEqual(call.args[0][0].children, ["a.txt", "b.txt"])
        self.assertEqual(call.args[2], "zh")
        self.assertTrue(call.kwargs["want_notes"])

    def _seed_categorized_row(self, server: Any) -> dict[str, Any]:
        """A row the user already filed under 工作, with no note."""
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            item = self._add(server, "A", "https://a.test")
        server.dispatcher.dispatch(
            "resources.update",
            {
                "mode": "links",
                "id": item["id"],
                "name": "A",
                "target": "https://a.test",
                "category": "工作",
            },
        )
        return item

    def _run_notes(self, server: Any, reply: dict[str, Any], ids: list[str]) -> int:
        with mock.patch("resource_hub_core.protocol.AiClient") as client_cls:
            client_cls.return_value.suggest_categories.return_value = reply
            return server.dispatcher._tag_notes(
                [("links", item_id) for item_id in ids]
            )

    def test_backfill_writes_a_note_without_touching_the_category(self) -> None:
        server = self._server()
        item = self._seed_categorized_row(server)
        written = self._run_notes(
            server,
            {
                "suggestions": [
                    {"id": item["id"], "category": "AI", "note": "团队代码托管"}
                ]
            },
            [item["id"]],
        )
        self.assertEqual(written, 1)
        self.assertEqual(
            self._field(server, "links", item["id"], "note"), "团队代码托管"
        )
        # The model suggested "AI"; the row must keep the user's 工作.
        self.assertEqual(
            self._field(server, "links", item["id"], "category"), "工作"
        )

    def test_backfill_skips_rows_that_already_have_a_note(self) -> None:
        server = self._server()
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            item = self._add(server, "A", "https://a.test")
        server.dispatcher.dispatch(
            "resources.update",
            {
                "mode": "links",
                "id": item["id"],
                "name": "A",
                "target": "https://a.test",
                "note": "我自己写的",
            },
        )
        written = self._run_notes(
            server,
            {"suggestions": [{"id": item["id"], "note": "AI 写的"}]},
            [item["id"]],
        )
        self.assertEqual(written, 0)
        self.assertEqual(
            self._field(server, "links", item["id"], "note"), "我自己写的"
        )

    def test_undo_notes_clears_notes_but_keeps_categories(self) -> None:
        server = self._server()
        item = self._seed_categorized_row(server)
        self._run_notes(
            server,
            {"suggestions": [{"id": item["id"], "note": "AI 写的"}]},
            [item["id"]],
        )
        undone = server.dispatcher.dispatch("ai.undoNotes", {})
        self.assertEqual(undone["restored"], 1)
        self.assertEqual(self._field(server, "links", item["id"], "note"), "")
        self.assertEqual(
            self._field(server, "links", item["id"], "category"), "工作"
        )

    def test_backfill_queues_only_rows_without_a_note(self) -> None:
        server = self._server()
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            blank = self._add(server, "A", "https://a.test")
            filled = self._add(server, "B", "https://b.test")
        server.dispatcher.dispatch(
            "resources.update",
            {
                "mode": "links",
                "id": filled["id"],
                "name": "B",
                "target": "https://b.test",
                "note": "已有",
            },
        )
        with mock.patch.object(type(server.dispatcher), "_backfill_worker"):
            result = server.dispatcher.dispatch("ai.backfill", {})
        self.assertEqual(result["total"], 1)
        self.assertEqual(
            server.dispatcher._ai_backfill_targets, [("links", blank["id"])]
        )

    def test_backfill_is_refused_without_a_key(self) -> None:
        server = self._server()
        server.dispatcher.dispatch("ai.setKey", {"apiKey": ""})
        with self.assertRaises(ProtocolError) as caught:
            server.dispatcher.dispatch("ai.backfill", {})
        self.assertEqual(caught.exception.code, "ai_not_configured")

    def test_undo_restores_uncategorized_and_is_one_shot(self) -> None:
        server = self._server()
        with mock.patch.object(type(server.dispatcher), "_kick_ai"):
            item = self._add(server, "A", "https://a.test")
        self._run_tag(
            server,
            {"suggestions": [{"id": item["id"], "category": "Work"}]},
            [item["id"]],
        )
        self.assertEqual(self._categories(server)[item["id"]], "Work")

        undone = server.dispatcher.dispatch("ai.undoCategorize", {})
        self.assertEqual(undone["restored"], 1)
        self.assertEqual(self._categories(server)[item["id"]], UNCATEGORIZED)
        again = server.dispatcher.dispatch("ai.undoCategorize", {})
        self.assertEqual(again["restored"], 0)


class AiPromptTests(unittest.TestCase):
    """Phase 30: what the model is told, and what it is not."""

    def test_links_send_the_url_but_never_a_path(self) -> None:
        entry = _payload_item(
            AiItem(mode="links", id="l", name="GitHub", target="https://github.com", kind="link")
        )
        self.assertEqual(entry["url"], "https://github.com")
        self.assertNotIn("parent", entry)
        self.assertNotIn("children", entry)

    def test_folders_send_the_parent_name_and_child_names(self) -> None:
        entry = _payload_item(
            AiItem(
                mode="folders",
                id="f",
                name="proj",
                target=r"D:\Work\proj",
                kind="folder",
                children=["src", "README.md"],
            )
        )
        self.assertEqual(entry["parent"], "Work")
        self.assertEqual(entry["children"], ["src", "README.md"])
        self.assertNotIn("path", entry)

    def test_reasons_are_omitted_when_not_needed(self) -> None:
        # The backfill throws reasons away; asking for them was most of the
        # reply and the reason a 40-row batch overran the output budget.
        without = _system_prompt(["AI"], "zh", True, False)
        with_reasons = _system_prompt(["AI"], "zh", True, True)
        self.assertNotIn("reason", without)
        self.assertIn('"note"', without)
        self.assertIn("reason", with_reasons)

    def test_notes_are_only_requested_when_asked_for(self) -> None:
        with_notes = _system_prompt(["AI"], "zh", True)
        without = _system_prompt(["AI"], "zh", False)
        self.assertIn("short note", with_notes)
        self.assertIn("Simplified Chinese", with_notes)
        self.assertNotIn("short note", without)
        self.assertIn("English", _system_prompt([], "en", True))


if __name__ == "__main__":
    unittest.main()
