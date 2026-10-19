# 抽屉 Drawer

A Windows desktop launcher for the things you use every day: frequently visited
websites, local folders and single files.

- Two resource types: links (sites) and local paths (folders / files)
- Search, category filters, favorites (a star, no longer pinned)
- Drag rows or cards to arrange the order (list and grid), with a 5-second undo
- Click a resource to open the details panel: a zoomable folder mind map (folders)
  or link/file details, without leaving the list
- Drag and drop files or folders onto the window to add them
- Import / export JSON backups (compatible with the legacy Python version)
- Quick-panel hotkeys: `Ctrl + Alt + Shift + L` (sites tree) and `Ctrl + Alt + Shift + F`
  (folders tree) open a compact Spotlight-style tree instead of the full window
- Browser bookmark sync: new Chrome / Edge bookmarks are imported automatically
  (reads the local bookmark files, read-only); an optional unpacked extension
  adds two-way delete/rename sync (browser extension folder ships with the app)
- Explorer context menu: right-click a folder icon or the empty area inside a
  folder (Windows 11: under "Show more options") to add it to the folders list and
  bring the app to the front; the entries can be switched off in Settings
- Optional AI category suggestions (experimental, off by default): a DeepSeek or
  OpenAI-compatible endpoint proposes categories for uncategorized sites/folders;
  nothing is written until you review and apply the suggestions (API key stored
  with Windows DPAPI)
- Tray icon, global hotkey (`Ctrl + Alt + Space` by default), optional startup
- Chinese / English UI, light / dark theme
- Path health check, open, reveal in Explorer

## User Guide

A Chinese user manual is included with the app:
[抽屉使用说明.docx](docs/抽屉使用说明.docx) /
[PDF](docs/抽屉使用说明.pdf).
It covers installation, adding resources, the folder mind map, quick-panel
hotkeys, browser bookmark sync, the Explorer context menu, AI suggestions,
data/backup, shortcuts and troubleshooting.

See [CHANGELOG.md](CHANGELOG.md) for the tagged milestones (`v0.1.0` … `v1.0.2`).

## Implementations

This repository contains two generations of the app:

| Path | Role |
|---|---|
| `app/` + `backend/` | **Current**: Flutter Windows client + headless Python backend, talking JSON Lines over stdio |
| `resource_hub.pyw` | Legacy single-file Tkinter app, kept for reference and rollback; no longer developed |

## Download / Install

Build outputs are **not committed** (`release/` is git-ignored). Build the package
locally:

Requirements:

- Flutter 3.47+ with Windows desktop support
- Visual Studio 2022 Build Tools (Desktop development with C++)
- Python 3.11+ with PyInstaller (for the frozen backend)

```powershell
# Edit $python and $flutterRoot at the top of the script to match your machine first.
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-flutter-release.ps1
```

Output: `release\ResourceHub-Desktop-<timestamp>\`. Double-click `resource_hub.exe`
to start. Keep the folder writable — data files are stored next to the executable.

## Run From Source

Start the Flutter client and it locates and launches the backend for you:

```powershell
cd app
flutter run -d windows
```

If Python is not on `PATH`, point `RH_PYTHON` at the interpreter. The backend can
also be started by hand:

```powershell
python backend\main.py [data-dir]
```

Environment overrides used by the client: `RH_PYTHON`, `RH_BACKEND_SCRIPT`,
`RH_BACKEND_EXE`, `RH_DATA_DIR`.

## Project Layout

```
app/                      Flutter client (lib/ = source, windows/ = native shell)
backend/                  Python business layer + JSON Lines protocol server
migration/                Migration record: audit, design system, ADRs, protocol,
                          shell integration, packaging, UI refactor, screenshots
resource_hub.pyw          Legacy Tkinter implementation (reference only)
build-flutter-release.ps1 Package builder (Flutter client + frozen backend)
release/                  Build output (git-ignored)
```

## Data Files

At runtime the app reads and writes, next to the executable (or the repository
root when running from source):

- `sites.json` — website favorites
- `folders.json` — local folder / file favorites
- `settings.json` — language, theme, global hotkey, startup

These files are git-ignored. Sample data lives in `sites.sample.json` and
`folders.sample.json`; the formats are unchanged from the legacy Python version,
so existing data can be migrated as-is.

## Tests

```powershell
cd app
flutter test                                  # 50 tests: widgets, protocol, JSON

cd backend
python -m unittest discover -s tests -t .     # 167 tests
```

## Notes

- Dropping a folder stores only that folder path; its contents are not imported.
- Dropping a file stores only that file path.
- Closing the window hides it to the tray — use the tray menu to quit.

## License

MIT
