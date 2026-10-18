# resource_hub_core

Headless business layer for Resource Hub. Extracted from `resource_hub.pyw` in
Phase 3 of the migration; see `../migration/phase3-business-layer.md`.

**No UI dependency.** Importing this package creates no Tk root and loads no
pystray. Only the standard library is used.

## Usage

```python
from pathlib import Path
from resource_hub_core import ResourceService, SettingsStore

service = ResourceService(Path(r"D:\Apps\ResourceHub"))
service.load()                      # raises CorruptDataError on unreadable data

service.add("links", name="GitHub", target="github.com")   # https:// is added
service.visible("folders", query="设计", favorites_only=True)
service.check_paths("folders")

settings = SettingsStore(Path(r"D:\Apps\ResourceHub\settings.json")).load()
```

`mode` is `"links"` (sites.json) or `"folders"` (folders.json).

## Errors

`ValidationError` / `DuplicateError` carry a **legacy i18n key** (`enter_link_name`,
`duplicate_folder_path`, …) rather than a sentence, so the UI can translate them
with the existing string table:

```python
try:
    service.add("links", name="", target="https://a.example")
except ValidationError as exc:
    message = strings.t(exc.key)
```

## Durability rules (ADR-001 D3)

- Writes are atomic (temp file + `fsync` + `os.replace`).
- A file that exists but cannot be parsed raises `CorruptDataError` and is left
  **untouched** — it is never overwritten with sample data.
- Sample data is written only when the file is **absent**; an empty list stays
  empty.
- The previous contents are kept as `<name>.bak` before each write.

## Tests

```powershell
D:\miniconda3\python.exe -m unittest discover -s tests -t .
```

138 tests, no third-party packages required.

## Protocol server

`main.py` runs the backend as a JSON Lines server on stdin/stdout:

```powershell
D:\miniconda3\python.exe backend\main.py "D:\Apps\ResourceHub"
```

```
→ {"id":1,"method":"resources.list","params":{"mode":"folders"}}
← {"id":1,"ok":true,"result":{"items":[...],"total":11,"visible":11}}
← {"event":"hotkey","payload":{"action":"toggle"}}
```

See `migration/phase4-ipc-protocol.md` for the full frame spec, method table and
error codes. stdout carries protocol frames only; diagnostics go to stderr.
