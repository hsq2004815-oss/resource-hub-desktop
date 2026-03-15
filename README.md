# Resource Hub Desktop

Resource Hub Desktop is a Windows desktop tool for managing:

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

If someone downloads the whole repository ZIP and just wants to use the app:

1. Open the `release\ResourceHub-Ultimate-EXE-20260316` folder
2. Double-click `ResourceHubPython.exe`

No Python installation is required for that EXE version.

## Project Structure

- `resource_hub.pyw`: main desktop application
- `requirements-python.txt`: Python dependencies
- `build-resource-hub-python.ps1`: build script for the Windows EXE
- `start-resource-hub-python.bat`: start script for source mode
- `Install-ResourceHub-Python-Shortcut.vbs`: create a desktop shortcut for source mode
- `Install-ResourceHub-Exe-Shortcut.vbs`: create a desktop shortcut for the built EXE
- `sites.sample.json`: sample website data
- `folders.sample.json`: sample local resource data
- `release/`: ready-to-run packaged EXE version

## Requirements

- Windows
- Python 3.11+ recommended

## Run From Source

Install dependencies:

```powershell
python -m pip install -r requirements-python.txt
```

Start the app:

```powershell
python resource_hub.pyw
```

Or double-click:

- `start-resource-hub-python.bat`

## Build EXE

Install build tools first:

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

The application reads and writes:

- `sites.json`
- `folders.json`

These runtime data files are ignored by Git.

For repository examples, use:

- `sites.sample.json`
- `folders.sample.json`

## Notes

- Dragging a folder into the app only stores that folder path.
- Dragging a file into the app only stores that file path.
- The app does not import all contents inside a dropped folder.

## License

MIT
