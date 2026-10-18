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

The stored **array order is the display order**. `resources.reorder` accepts the
complete id list of a collection and persists a new order; `resources.list`
returns entries in that order (favourites are no longer pinned to the top —
that changed in Phase 8 so manual drag ordering is the single source of truth).

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

## Browser bookmarks (Phase 17)

The backend can import the local Chrome/Edge bookmarks into `sites.json` — no
extension and no network. Browser files are only ever **read**; the imported
links are appended at the end of the collection once and each URL is remembered
in `.resourcehub-meta.json` so deleting a resource never resurrects it.

```
→ {"id":20,"method":"bookmarks.status","params":{}}
← {"id":20,"ok":true,"result":{"enabled":true,"customDir":"",
     "profiles":[{"label":"Chrome · Default","path":"C:\\...\\Bookmarks",
                  "bookmarks":42}],"lastSyncAt":null,"syncedUrls":0}}
→ {"id":21,"method":"bookmarks.sync","params":{}}
← {"event":"bookmarks","payload":{"added":7,"lastSyncAt":"2026-04-22T13:53:49+08:00",
     "profiles":[...]}}
← {"id":21,"ok":true,"result":{"added":7,"skipped":35,"total":42,
     "profiles":[...],"lastSyncAt":"2026-04-22T13:53:49+08:00"}}
```

Settings gained `bookmarkSyncEnabled` (default `true`) and `bookmarkCustomDir`
(default `""`; accepts a `Bookmarks` file, a profile directory or a browser
`User Data` directory). While the JSON Lines server runs, a daemon watcher polls
the discovered files (mtime/size, 0.6 s debounce) and emits the same
`bookmarks` event when it imports something. `RH_BROWSER_DATA_DIRS` (a
`os.pathsep`-separated list of `User Data` roots) replaces the Windows default
roots and is what the tests use, so they never read the real browser profile.

## Tests

```powershell
D:\miniconda3\python.exe -m unittest discover -s tests -t .
```

226 tests, no third-party packages required.

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

## Filesystem browsing (Phase 9)

The folder preview panel expands one directory level at a time through read-only
methods; they never touch `sites.json` / `folders.json`:

```
→ {"id":9,"method":"fs.children","params":{"path":"D:\\Books"}}
← {"id":9,"ok":true,"result":{"path":"D:\\Books","entries":[
     {"name":"Design","path":"D:\\Books\\Design","kind":"folder","isLink":false}],
     "total":42,"shown":42,"truncated":false}}
→ {"id":10,"method":"fs.open","params":{"path":"D:\\Books\\Design"}}
→ {"id":11,"method":"fs.reveal","params":{"path":"D:\\Books\\Design"}}
```

`fs.children` reads a single level, sorts folders first (then name), returns at
most 200 entries while still counting the directory (so the UI can show "N more
items"), and maps missing/not-a-directory/permission errors to i18n keys
(`fs_not_found`, `fs_not_directory`, `fs_permission_denied`, `fs_unreadable`).
See `migration/phase9-folder-preview.md`.
