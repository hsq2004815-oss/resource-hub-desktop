# 抽屉 Drawer

[English](README.md) · [简体中文](README.zh-CN.md)

<p align="center">
  <img src="docs/images/demo.gif" width="820" alt="Drawer demo: opening the quick panel with a hotkey and opening a folder">
</p>

<p align="center">
  <b>One drawer for every website, folder and file you open every day.</b><br>
  A Windows quick launcher that stays out of your way — one hotkey, a few letters, <kbd>Enter</kbd>.
</p>

<p align="center">
  <a href="https://github.com/hsq2004815-oss/resource-hub-desktop/releases/latest"><img src="https://img.shields.io/github/v/release/hsq2004815-oss/resource-hub-desktop?sort=semver&display_name=tag&color=2ea44f" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D4" alt="Windows 10 / 11">
  <img src="https://img.shields.io/github/license/hsq2004815-oss/resource-hub-desktop" alt="MIT License">
  <img src="https://img.shields.io/github/downloads/hsq2004815-oss/resource-hub-desktop/total?color=blue" alt="Downloads">
  <img src="https://img.shields.io/github/last-commit/hsq2004815-oss/resource-hub-desktop" alt="Last commit">
</p>

<p align="center">
  <a href="https://github.com/hsq2004815-oss/resource-hub-desktop/releases/latest"><img src="https://img.shields.io/badge/Download-Windows_64--bit-2ea44f?style=for-the-badge" alt="Download for Windows"></a>
</p>

**Portable ZIP, ~22 MB.** Unzip the whole folder, run `resource_hub.exe`. No installer, no Python, no account.

## Why Drawer?

Windows keeps the things you use every day in three or four different places: bookmarks in the
browser, pinned folders in Explorer, shortcuts on the desktop. Drawer puts them into one
searchable list and one hotkey away.

- **Websites, folders and files — one list.** Same search box, same keyboard flow, different icons.
- **Open a folder without opening Explorer.** Click a folder row and its contents unfold as a mind
  map you can zoom, pan and drill into.
- **A quick panel, not a window.** `Ctrl + Alt + Shift + L` / `F` drops a compact tree in the middle
  of the screen: type, arrow, Enter — gone.
- **Nothing leaves your machine.** No account, no sync server, no telemetry. All data is a few JSON
  files next to the executable.

## Screenshots

<p align="center">
  <img src="docs/images/main-window.png" width="820" alt="Main window: search box, category filter, resource list"><br>
  <sub><b>Main window</b> — one searchable list for websites, folders and files. List or grid, drag to reorder, favorites pinned on top.</sub>
</p>

<p align="center">
  <img src="docs/images/folder-mindmap.png" width="420" alt="Folder details with a mind map"><br>
  <sub><b>Folder mind map</b> — click a folder row to unfold its contents. Zoom, pan, expand level by level; double-click to open, right-click to add a child.</sub>
</p>

<table>
<tr>
<td width="50%" align="center" valign="top">
  <img src="docs/images/quick-panel.png" width="300" alt="Quick panel"><br>
  <sub><b>Quick panel</b> — the compact tree behind <code>Ctrl+Alt+Shift+L/F</code>.</sub>
</td>
<td width="50%" align="center" valign="top">
  <img src="docs/images/settings.png" width="330" alt="Settings"><br>
  <sub><b>Settings</b> — language, theme, hotkeys, bookmark sync, AI suggestions.</sub>
</td>
</tr>
</table>

## Features

**Resource management**

- Two resource types: websites and local paths (folders or single files).
- Search by name, path, type, category or note; filter by category.
- Favorites pinned to the top; drag rows or cards to arrange the order, with a 5-second undo.
- List and grid views; drag files or folders from Explorer onto the window to add them.
- Import / export JSON backups (compatible with the legacy Python version).

**Quick panel**

- A compact Spotlight-style tree instead of the full window, centered on the current screen.
- `Ctrl + Alt + Shift + L` — websites; `Ctrl + Alt + Shift + F` — folders (both configurable).
- Optional mouse side buttons: back opens the websites panel, forward the folders panel. While the
  switch is on, Drawer takes over the mouse back / forward buttons.
- `↑` / `↓` select, `→` expand, `Enter` open, `Esc` close, `Tab` switch panel; type to search.

**Folder mind map**

- The details panel renders a folder's contents as an auto-laid-out mind map — no Explorer hopping.
- `Ctrl` + wheel to zoom, drag to pan, one click to reset to 100%.
- Double-click a node to open it; right-click to add it to the drawer.

**System integration**

- Chrome / Edge bookmark sync: new bookmarks are imported automatically from the local bookmark
  files (read-only). An optional unpacked MV3 extension adds two-way delete / rename sync; the
  extension folder ships with the app.
- Explorer context menu: right-click a folder background or folder icon → **Add to Drawer**
  (Windows 11: under "Show more options"). The entries can be switched off in Settings.
- Tray icon, close-to-tray, optional launch at startup, global hotkey with `Ctrl / Alt / Shift / Win`
  combinations.

**Optional AI category suggestions** (experimental, off by default)

- A DeepSeek or OpenAI-compatible endpoint proposes categories for uncategorized resources.
- Nothing is written until you review and apply the proposals; the API key is stored with Windows
  DPAPI and never committed.

**Quality of life**

- Path health check: missing paths are flagged; open or reveal any resource in Explorer.
- Chinese / English UI, light / dark / follow-system theme.
- 100% local, no account, no telemetry.

## Install

1. Download `Drawer-v*-win64.zip` from [Releases](https://github.com/hsq2004815-oss/resource-hub-desktop/releases/latest).
2. Unzip the **whole folder** to a writable place (e.g. `D:\Drawer`). Don't run it from inside the
   ZIP and don't put it in `Program Files`.
3. Run `resource_hub.exe`. If SmartScreen warns, choose **More info → Run anyway** — the executable
   is not code-signed.
4. The first launch creates sample resources; delete them and add your own.

Windows 10 / 11, 64-bit. Data lives next to the executable (`sites.json`, `folders.json`,
`settings.json`); backing up or moving the app is just copying the folder, and uninstalling is
deleting it.

## Hotkeys

| Shortcut | Action |
|---|---|
| `Ctrl + Alt + Space` | Show / hide the main window |
| `Ctrl + Alt + Shift + L` | Quick panel: websites |
| `Ctrl + Alt + Shift + F` | Quick panel: folders |
| Mouse Back / Mouse Forward (optional) | Quick panel: websites / folders |
| `↑` `↓` / `→` / `Enter` / `Esc` / `Tab` | Navigate / expand / open / close / switch panel |

Every hotkey is configurable in **Settings → Shortcuts**, including `Ctrl / Alt / Shift / Win`
combinations. The mouse side buttons are a separate switch in the same section.

## FAQ

**Is it free?** Yes — MIT licensed, free to use, modify and redistribute.

**Does it send anything to the internet?** No. The only network call is the optional AI suggestion
feature, and it uses the endpoint and API key you configure yourself.

**Why does Windows SmartScreen warn me?** The executable is not code-signed (that costs money and
this is a self-funded open-source project). The full source is in this repository; build it
yourself if you prefer.

**Is it the same as PowerToys Run or Everything?** No. Those search installed apps or index the
whole disk. Drawer holds the small set of websites, folders and files *you* chose, and can show a
folder's contents as a mind map without opening Explorer.

**Can I move it to another PC?** Yes — copy the whole folder, data files included.

**macOS / Linux?** Windows only for now.

## User guide

A Chinese user manual ships with the app and is also in this repository:
[抽屉使用说明.docx](docs/抽屉使用说明.docx) ·
[PDF](docs/抽屉使用说明.pdf).
It covers installation, adding resources, the folder mind map, quick-panel hotkeys, bookmark sync,
the Explorer menu, AI suggestions, data and backups, and troubleshooting.

See [CHANGELOG.md](CHANGELOG.md) for the tagged milestones (`v0.1.0` … `v1.1.0`).

## Build from source

Build outputs are **not committed** (`release/` is git-ignored). Build the package locally:

Requirements:

- Flutter 3.47+ with Windows desktop support
- Visual Studio 2022 Build Tools (Desktop development with C++)
- Python 3.11+ with PyInstaller (for the frozen backend)

```powershell
# Edit $python and $flutterRoot at the top of the script to match your machine first.
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-flutter-release.ps1
```

Output: `release\ResourceHub-Desktop-<timestamp>\`. Double-click `resource_hub.exe` to start. Keep
the folder writable — data files are stored next to the executable.

## Run from source

Start the Flutter client and it locates and launches the backend for you:

```powershell
cd app
flutter run -d windows
```

If Python is not on `PATH`, point `RH_PYTHON` at the interpreter. The backend can also be started by
hand:

```powershell
python backend\main.py [data-dir]
```

Environment overrides used by the client: `RH_PYTHON`, `RH_BACKEND_SCRIPT`, `RH_BACKEND_EXE`,
`RH_DATA_DIR`.

## Tests

```powershell
cd app
flutter test                                  # 75 tests: widgets, protocol, JSON

cd backend
python -m unittest discover -s tests -t .     # 335 tests (1 skipped: symlink)
```

That is 410 passing tests across the Flutter client and the Python backend.

## Under the hood

This repository contains two generations of the app:

| Path | Role |
|---|---|
| `app/` + `backend/` | **Current**: Flutter Windows client (~12k lines of Dart) + headless Python backend (~7.9k lines, stdlib only), talking JSON Lines over stdio |
| `resource_hub.pyw` | Legacy single-file Tkinter app (~2.9k lines), kept for reference and rollback; no longer developed |

The rewrite is documented phase by phase in [`migration/`](migration/): audit, design system,
business layer, IPC protocol, packaging, shell integration and 25 UI/feature phases. It doubles as
a readable case study of splitting a monolithic Tkinter app into a UI and a testable backend
**without changing the user's data format** — existing `sites.json` / `folders.json` files keep
working.

## Project layout

```
app/                      Flutter client (lib/ = source, windows/ = native shell)
backend/                  Python business layer + JSON Lines protocol server
docs/                     User manual (docx/pdf) and screenshots
migration/                Migration record: audit, design system, ADRs, protocol,
                          shell integration, packaging, UI refactor, screenshots
resource_hub.pyw          Legacy Tkinter implementation (reference only)
build-flutter-release.ps1 Package builder (Flutter client + frozen backend)
release/                  Build output (git-ignored)
```

## Data files

At runtime the app reads and writes, next to the executable (or the repository root when running
from source):

- `sites.json` — website favorites
- `folders.json` — local folder / file favorites
- `settings.json` — language, theme, global hotkey, startup

These files are git-ignored. Sample data lives in `sites.sample.json` and
`folders.sample.json`; the formats are unchanged from the legacy Python version, so existing data
can be migrated as-is.

## Notes

- Dropping a folder stores only that folder path; its contents are not imported.
- Dropping a file stores only that file path.
- Closing the window hides it to the tray — use the tray menu to quit.

## Contributing

Issues and pull requests are welcome. If Drawer saves you a few clicks a day, a ⭐ helps other
people find it.

## License

MIT License. Copyright (c) 2026 黄双全 (Huang Shuangquan).

Free to use, copy, modify, distribute and commercialize, provided the copyright notice is retained.
See [LICENSE](LICENSE) for the full text.
