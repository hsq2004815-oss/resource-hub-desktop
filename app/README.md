# Resource Hub — Flutter client

Windows desktop client for Resource Hub, built with Flutter 3 (Material 3) and a
native C++ runner that owns the tray icon, window lifecycle, drag-and-drop and
shell integration. All business logic lives in the Python backend at
`../backend`, reached over a JSON Lines protocol on stdio.

See the repository [README](../README.md) and `../migration/` for the migration
record and architecture decisions.

## Run

```powershell
flutter pub get
flutter run -d windows
```

The client finds `../backend/main.py` and starts it with the interpreter from
`RH_PYTHON`, or `python` / `py` on `PATH`. Overrides: `RH_BACKEND_SCRIPT`,
`RH_BACKEND_EXE`, `RH_DATA_DIR`.

VS Code run configurations (repository data, scratch data, dark + English) live in
`.vscode/launch.json`.

## Test

```powershell
flutter test
```

## Layout

```
lib/
  data/       backend bootstrap, repository, protocol models
  design/     design tokens + Material 3 theme
  features/   home screen, resource form, settings dialog
  l10n/       generated strings (from the Python string table) + UI-only keys
  platform/   stdio backend client, native shell channel, window control
  util/       formatters, hotkeys, JSON backup helpers
  widgets/    table, grid, fields, buttons, status bar
windows/runner  native shell: tray, single instance, drop target, shell dialogs
```
