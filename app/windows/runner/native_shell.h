#ifndef RUNNER_NATIVE_SHELL_H_
#define RUNNER_NATIVE_SHELL_H_

#include <windows.h>

#include <string>

// Thin wrappers around the Win32 shell pieces the Flutter client needs but that
// have no plugin dependency: common file dialogs and the Startup shortcut.
//
// Kept in the runner (not in the Python backend and not in a pub package) so the
// release build has no extra DLLs or Python dependencies — see ADR-002.
namespace native_shell {

// Shows the "select folder" dialog. Returns an empty string when cancelled.
std::wstring ShowFolderPicker(HWND owner);

// Shows the "open file" dialog. With |json_only| the file list is filtered to
// *.json (import), otherwise every file is offered (form path picker).
// Returns an empty string when cancelled.
std::wstring ShowFilePicker(HWND owner, bool json_only);

// Shows the "save JSON file" dialog with |suggested_name| pre-filled.
// Returns an empty string when cancelled.
std::wstring ShowJsonSaveDialog(HWND owner, const std::wstring& suggested_name);

// Absolute path of the Startup shortcut, or empty when it cannot be resolved.
std::wstring StartupShortcutPath();

// Creates (enabled) or removes (disabled) the Startup shortcut that launches
// this executable with --startup-hidden. Returns true on success.
bool SetLaunchAtStartup(bool enabled);

// Whether the Startup shortcut currently exists.
bool GetLaunchAtStartup();

// Phase 19: HKCU Explorer folder context-menu entry ("添加到抽屉").
//
// Writes only HKCU\Software\Classes\Directory\shell\ResourceHubAddFolder, so
// no elevation is needed and the entry can be removed at any time. On Windows 11
// Explorer lists it under "Show more options" (classic menu).
bool SetShellContextMenuEnabled(bool enabled);

// Whether the registry entry currently exists.
bool GetShellContextMenuEnabled();

// Opens a URL / file / folder with its default shell handler.
//
// Called from the runner, i.e. from the process that owns the foreground
// window: before handing off, it grants "set foreground" permission to the
// shell (AllowSetForegroundWindow(ASFW_ANY)). Without that, Explorer or the
// browser can be created behind the app window because a background process
// may not steal focus (Windows foreground lock). Returns false when the shell
// rejected the target, so the caller can fall back to the backend.
bool OpenTarget(const std::wstring& target);

// Opens the containing folder and selects |path| in Explorer
// (SHOpenFolderAndSelectItems, same foreground hand-off as OpenTarget).
bool RevealPath(const std::wstring& path);

}  // namespace native_shell

#endif  // RUNNER_NATIVE_SHELL_H_
