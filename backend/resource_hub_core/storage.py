"""JSON persistence with the durability fixes required by ADR-001 D3.

The legacy ``_load_json`` / ``_write_json`` pair (``resource_hub.pyw:1815-1824``)
had a real data-loss path: a truncated file parsed to ``[]``, and the caller then
overwrote it with sample data. This module changes four things:

1. Writes are atomic — temp file in the same directory, ``flush`` + ``fsync``,
   then ``os.replace``. A crash mid-write leaves the previous file intact.
2. Parse failures raise :class:`CorruptDataError` instead of returning ``[]``.
3. "First run" is decided by *file absence*, never by "parsed to empty".
4. The previous contents are copied to ``<name>.bak`` before every write.

Point 2 means callers must decide what to do on corruption. ``ResourceService``
refuses to touch the file and surfaces the error to the UI.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any


class StorageError(Exception):
    """Base class for persistence problems."""


class CorruptDataError(StorageError):
    """The file exists but cannot be parsed.

    Raised instead of silently returning an empty list — overwriting a file we
    failed to understand is exactly the data-loss path ADR-001 D3 removes.
    """

    def __init__(self, path: Path, detail: str) -> None:
        super().__init__(f"{path} is unreadable: {detail}")
        self.path = path
        self.detail = detail


class JsonFileStore:
    """Reads and writes one JSON file atomically."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @property
    def backup_path(self) -> Path:
        return self.path.with_name(self.path.name + ".bak")

    # -- reading -----------------------------------------------------------
    def load(self) -> Any:
        """Return the parsed payload.

        Raises:
            FileNotFoundError: the file does not exist (a legitimate first run).
            CorruptDataError: the file exists but is empty or not valid JSON.
        """
        if not self.path.exists():
            raise FileNotFoundError(str(self.path))
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError as exc:  # unreadable due to permissions / locks
            raise CorruptDataError(self.path, f"cannot read: {exc}") from exc
        if not text.strip():
            raise CorruptDataError(self.path, "file is empty")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise CorruptDataError(
                self.path, f"invalid JSON at line {exc.lineno}: {exc.msg}"
            ) from exc

    def load_or_none(self) -> Any | None:
        """Like :meth:`load`, but returns ``None`` when the file is absent."""
        try:
            return self.load()
        except FileNotFoundError:
            return None

    # -- writing -----------------------------------------------------------
    def save(self, data: Any) -> None:
        """Atomically replace the file, keeping the previous version as ``.bak``."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                shutil.copy2(self.path, self.backup_path)
            except OSError:
                # A failed backup must not block the write; the atomic replace
                # still protects against a torn file.
                pass
        atomic_write_text(
            self.path,
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        )


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` so readers never observe a partial file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        finally:
            pass
        raise
