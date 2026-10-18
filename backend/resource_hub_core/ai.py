"""DeepSeek-compatible AI category suggestions and the encrypted key store.

Phase 22. Two independent pieces live here:

* :class:`AiKeyStore` keeps the API key in ``<app_dir>/.resourcehub-ai-key``,
  encrypted with Windows DPAPI (user scope) and stored as base64 text. The key
  deliberately does **not** live in ``settings.json``: that file is plain JSON.
  The key is never logged, printed or put into an exception message.
* :class:`AiClient` is a small OpenAI-compatible ``/chat/completions`` client
  built on :mod:`urllib.request` (stdlib only). It never writes to stdout — the
  backend's stdout is the protocol stream — and it never sends a full local
  folder path: folders are reduced to name + immediate parent directory name.

Tests inject ``opener`` into :class:`AiClient`, so the suite never touches the
network.

Privacy / tradeoff notes
------------------------
* Links send their URL (needed to categorise them correctly); folders send only
  the folder name and its parent directory's *basename*, never the full path.
* The request is synchronous: the JSON Lines server serves one request at a
  time, so an in-flight suggestion call (up to ``timeout`` seconds) blocks the
  other protocol calls. The UI already shows a "requesting suggestions" status.
"""

from __future__ import annotations

import base64
import ctypes
import json
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .storage import atomic_write_text

#: File next to ``settings.json`` holding the DPAPI-encrypted API key.
AI_KEY_FILENAME = ".resourcehub-ai-key"

#: OpenAI-compatible chat endpoint path appended to the configured base URL.
CHAT_COMPLETIONS_PATH = "/chat/completions"

#: ``CryptProtectData`` flag: never show UI (the backend has no window).
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class AiError(Exception):
    """An AI request failed. ``code`` is a stable, log-safe reason."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        #: Safe to show to the user / write to the protocol error frame.
        self.detail = detail


class AiKeyStoreError(Exception):
    """The platform key store could not encrypt or decrypt the key."""


if sys.platform == "win32":

    from ctypes import wintypes

    class _DataBlob(ctypes.Structure):
        """``CRYPTOAPI_BLOB``: a length + byte pointer pair."""

        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    def _bind_crypt_function(name: str) -> Any:
        function = getattr(_crypt32, name)
        function.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,  # description (NULL)
            ctypes.POINTER(_DataBlob),  # optional entropy (NULL)
            ctypes.c_void_p,  # reserved (NULL)
            ctypes.c_void_p,  # prompt struct (NULL)
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        function.restype = wintypes.BOOL
        return function

    _crypt_protect = _bind_crypt_function("CryptProtectData")
    _crypt_unprotect = _bind_crypt_function("CryptUnprotectData")
    _local_free = _kernel32.LocalFree
    _local_free.argtypes = [ctypes.c_void_p]
    _local_free.restype = ctypes.c_void_p


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    """Run one DPAPI call in the current user's scope.

    User scope is the default (no ``CRYPTPROTECT_LOCAL_MACHINE``): another
    Windows account cannot decrypt the file even if it can read it.
    """
    if sys.platform != "win32":
        raise AiKeyStoreError("the DPAPI key store is only available on Windows")

    # create_string_buffer needs a size >= 1; cbData still carries the real
    # length, so a lone NUL byte is never interpreted as part of the payload.
    buffer = ctypes.create_string_buffer(data, max(len(data), 1))
    data_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    data_out = _DataBlob()
    action = "CryptProtectData" if protect else "CryptUnprotectData"
    try:
        call = _crypt_protect if protect else _crypt_unprotect
        ok = call(
            ctypes.byref(data_in),
            None,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(data_out),
        )
        if not ok:
            raise AiKeyStoreError(
                f"DPAPI {action} failed (windows error {ctypes.get_last_error()})"
            )
        return ctypes.string_at(data_out.pbData, data_out.cbData)
    finally:
        if data_out.pbData:
            _local_free(data_out.pbData)


class AiKeyStore:
    """Stores one API key in a DPAPI-encrypted file.

    ``load`` never raises for a missing/corrupt/foreign-user file: it returns
    ``None`` so ``ai.status`` can simply report "not configured". Writes use the
    same atomic temp+replace helper as the JSON stores, so a crash never leaves
    a half-written key file.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def has_key(self) -> bool:
        """Whether a non-empty key file exists (it may still fail to decrypt)."""
        try:
            return self.path.is_file() and self.path.stat().st_size > 0
        except OSError:
            return False

    def load(self) -> str | None:
        """Return the decrypted API key, or ``None`` when unavailable."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            return None
        token = text.strip()
        if not token:
            return None
        try:
            encrypted = base64.b64decode(token.encode("ascii"), validate=True)
        except ValueError:
            return None
        try:
            key = _dpapi(encrypted, protect=False).decode("utf-8")
        except (AiKeyStoreError, UnicodeDecodeError):
            return None
        return key or None

    def save(self, api_key: str) -> None:
        """Encrypt ``api_key`` and replace the key file."""
        key = str(api_key).strip()
        if not key:
            raise ValueError("the API key must not be empty")
        encrypted = _dpapi(key.encode("utf-8"), protect=True)
        token = base64.b64encode(encrypted).decode("ascii")
        atomic_write_text(self.path, token + "\n")

    def clear(self) -> None:
        """Delete the key file (a missing file is not an error)."""
        self.path.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class AiItem:
    """One resource reduced to the fields that may leave the machine."""

    mode: str
    id: str
    name: str
    target: str
    kind: str = "link"


def _system_prompt(existing_categories: Sequence[str]) -> str:
    """Instructions for the model: strict JSON only, prefer known categories."""
    if existing_categories:
        categories = ", ".join(existing_categories)
    else:
        categories = "(none yet)"
    return (
        "You categorise saved links and folders for a personal resource manager. "
        f"The user's existing categories are: {categories}. "
        "For every input item choose exactly one category: 1-3 words, at most "
        "40 characters. Prefer an existing category when it fits; otherwise "
        "propose a new, short category. "
        "Reply with ONLY a JSON array, without prose or markdown fences. Each "
        'element must be an object like {"id": "<input id>", "category": '
        '"<category>", "reason": "<short reason, at most 200 characters>"}. '
        "Return one object per input item and use every input id exactly once."
    )


def _payload_item(item: AiItem) -> dict[str, Any]:
    """Build one request entry without ever including a full folder path."""
    entry: dict[str, Any] = {
        "id": item.id,
        "kind": item.kind,
        "name": item.name,
    }
    if item.mode == "links":
        # A link needs its URL to be categorised; that is what the user keeps
        # in the app already.
        entry["url"] = item.target
    else:
        # Privacy: only the parent directory's *name*, never the path.
        parent = Path(item.target).parent.name
        if parent:
            entry["parent"] = parent
    return entry


def _clip(value: Any, limit: int = 200) -> str:
    """One-line, bounded text for error details (never the API key)."""
    return " ".join(str(value).split())[:limit]


def _parse_json_array(content: str) -> list[dict[str, Any]]:
    """Extract the model's JSON array from its message content.

    Slicing from the first ``[`` to the last ``]`` also strips the ```json
    fences DeepSeek sometimes adds, without relying on a fence being present.
    """
    start = content.find("[")
    end = content.rfind("]")
    if start == -1 or end < start:
        raise AiError("invalid_response", "the AI reply did not contain a JSON array")
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AiError(
            "invalid_response", f"the AI reply was not valid JSON: {exc.msg}"
        ) from exc
    if not isinstance(parsed, list):
        raise AiError("invalid_response", "the AI reply was not a JSON array")
    return [entry for entry in parsed if isinstance(entry, dict)]


def _extract_content(payload: Mapping[str, Any]) -> str:
    """Read ``choices[0].message.content`` from an OpenAI-style reply."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AiError("invalid_response", "the AI reply has no choices")
    first = choices[0]
    message = first.get("message") if isinstance(first, Mapping) else None
    content = message.get("content") if isinstance(message, Mapping) else None
    if not isinstance(content, str) or not content.strip():
        raise AiError("invalid_response", "the AI reply has no message content")
    return content


class AiClient:
    """Minimal OpenAI-compatible chat client for category suggestions.

    ``opener`` is injectable for tests: any callable
    ``opener(request, timeout=...) -> response`` with a ``read()`` method works.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout: float = 60,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self._endpoint = str(base_url).rstrip("/") + CHAT_COMPLETIONS_PATH
        self._model = str(model)
        self._api_key = str(api_key)
        self._timeout = timeout
        self._open = opener or urllib.request.urlopen

    def suggest_categories(
        self,
        items: Sequence[AiItem],
        existing_categories: Sequence[str],
    ) -> dict[str, Any]:
        """POST one completion request. Returns ``{"model", "suggestions"}``.

        ``suggestions`` is the raw list parsed from the model reply; validating
        ids / categories is the dispatcher's job because only it can re-read
        the live collections.
        """
        payload = [_payload_item(item) for item in items]
        body = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": _system_prompt(existing_categories),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        payload, ensure_ascii=False, separators=(",", ":")
                    ),
                },
            ],
            "temperature": 0.1,
            "max_tokens": 1500,
        }
        reply = self._post(body)
        return {
            "model": self._model,
            "suggestions": _parse_json_array(_extract_content(reply)),
        }

    # -- transport ---------------------------------------------------------
    def _post(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Send the request and decode the JSON reply; failures become AiError."""
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            response = self._open(request, timeout=self._timeout)
            try:
                raw = response.read()
            finally:
                close = getattr(response, "close", None)
                if close is not None:
                    close()
        except urllib.error.HTTPError as exc:
            # The body is not echoed: a proxy or the endpoint could reflect
            # request data, and error details end up in the UI / protocol frame.
            raise AiError("http_error", _clip(f"HTTP {exc.code} {exc.reason or ''}")) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise AiError("timeout", "the AI request timed out") from exc
            raise AiError(
                "network_error", _clip(f"network error: {exc.reason}")
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise AiError("timeout", "the AI request timed out") from exc
        except OSError as exc:
            raise AiError("network_error", _clip(f"network error: {exc}")) from exc

        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise AiError(
                "invalid_response", "the AI endpoint returned invalid JSON"
            ) from exc
        if not isinstance(decoded, dict):
            raise AiError(
                "invalid_response", "the AI endpoint returned a non-object reply"
            )
        return decoded
