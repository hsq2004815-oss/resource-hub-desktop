# Resource Hub Desktop

A Windows desktop tool for managing:

- Common websites
- Local folders
- Single files

It supports:

- Chinese / English switching
- Favorites / pin-to-top
- Search and category filters
- Import / export JSON backups
- Local path checking
- Drag and drop for files and folders
- Building a standalone `.exe`

## Quick Start For Normal Users

If you just want to use the app without installing Python:

1. Open `release\ResourceHub-Ultimate-EXE-20260316`
2. Double-click `ResourceHubPython.exe`

The EXE version can run directly on Windows without installing Python.

## Project Structure

- `resource_hub.pyw`: main desktop application
- `requirements-python.txt`: Python dependencies
- `build-resource-hub-python.ps1`: Windows EXE build script
- `start-resource-hub-python.bat`: source-mode launcher
- `Install-ResourceHub-Python-Shortcut.vbs`: desktop shortcut script for source mode
- `Install-ResourceHub-Exe-Shortcut.vbs`: desktop shortcut script for the EXE build
- `sites.sample.json`: sample website data
- `folders.sample.json`: sample local resource data
- `release/`: packaged EXE version ready to run

## Run From Source

Install dependencies:

```powershell
python -m pip install -r requirements-python.txt
```

Run the app:

```powershell
python resource_hub.pyw
```

Or double-click:

- `start-resource-hub-python.bat`

## Build EXE

Install dependencies and build tools first:

```powershell
python -m pip install -r requirements-python.txt
python -m pip install pyinstaller
```

Then build:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-resource-hub-python.ps1
```

Build output:

- `dist\ResourceHubPython\ResourceHubPython.exe`

## Data Files

At runtime, the app reads and writes:

- `sites.json`
- `folders.json`

These runtime data files are ignored by Git.

Repository examples use:

- `sites.sample.json`
- `folders.sample.json`

## Notes

- Dropping a folder into the app only stores that folder path.
- Dropping a file into the app only stores that file path.
- The app does not import every file inside a dropped folder.

## License

MIT
