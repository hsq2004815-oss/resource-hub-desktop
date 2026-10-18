#include "native_shell.h"

#include <shellapi.h>
#include <shlobj.h>
#include <shobjidl.h>

#include <string>

#include "window_messages.h"

namespace {

// COM smart-pointer-ish helper: MSVC's wrl is not available in the runner, and a
// custom deleter would hide which call failed. Keep it explicit but short.
template <typename T>
void SafeRelease(T** value) {
  if (*value != nullptr) {
    (*value)->Release();
    *value = nullptr;
  }
}

std::wstring PathFromShellItem(IShellItem* item) {
  if (item == nullptr) {
    return std::wstring();
  }
  PWSTR raw = nullptr;
  if (FAILED(item->GetDisplayName(SIGDN_FILESYSPATH, &raw)) || raw == nullptr) {
    return std::wstring();
  }
  std::wstring result(raw);
  ::CoTaskMemFree(raw);
  return result;
}

// Shared setup for the two open-file dialogs.
IFileOpenDialog* CreateOpenDialog(HWND owner,
                                  bool pick_folders,
                                  bool json_only,
                                  const std::wstring& title) {
  IFileOpenDialog* dialog = nullptr;
  if (FAILED(::CoCreateInstance(CLSID_FileOpenDialog, nullptr,
                                CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&dialog)))) {
    return nullptr;
  }
  DWORD options = 0;
  if (FAILED(dialog->GetOptions(&options))) {
    options = 0;
  }
  options |= FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST;
  if (pick_folders) {
    options |= FOS_PICKFOLDERS;
  } else {
    options |= FOS_FILEMUSTEXIST;
  }
  dialog->SetOptions(options);
  if (!title.empty()) {
    dialog->SetTitle(title.c_str());
  }
  if (!pick_folders && json_only) {
    const COMDLG_FILTERSPEC filters[] = {{L"JSON", L"*.json"}};
    dialog->SetFileTypes(1, filters);
    dialog->SetDefaultExtension(L"json");
  }
  if (FAILED(dialog->Show(owner))) {
    SafeRelease(&dialog);
    return nullptr;
  }
  return dialog;
}

std::wstring ExecutablePath() {
  std::wstring buffer(MAX_PATH, L'\0');
  for (;;) {
    const DWORD length =
        ::GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
    if (length == 0) {
      return std::wstring();
    }
    if (length < buffer.size()) {
      buffer.resize(length);
      return buffer;
    }
    buffer.resize(buffer.size() * 2);
  }
}

// Phase 19: HKCU Explorer folder context-menu entries.
//
// Two variants share the executable and the switch:
//  - Directory\shell        -> right-clicking a folder icon, argument "%1"
//  - Directory\Background   -> right-clicking the empty area inside a folder,
//                              argument "%V" (the folder currently open)
constexpr wchar_t kShellMenuKey[] =
    L"Software\\Classes\\Directory\\shell\\ResourceHubAddFolder";
constexpr wchar_t kShellMenuBackgroundKey[] =
    L"Software\\Classes\\Directory\\Background\\shell\\ResourceHubAddFolder";

bool SetRegistryString(HKEY key, const wchar_t* name, const std::wstring& value) {
  const DWORD bytes = static_cast<DWORD>((value.size() + 1) * sizeof(wchar_t));
  return ::RegSetValueExW(key, name, 0, REG_SZ,
                          reinterpret_cast<const BYTE*>(value.c_str()),
                          bytes) == ERROR_SUCCESS;
}

// |label| is UTF-16 (escaped at the call sites); |placeholder| is %1 or %V.
bool CreateMenuEntry(const wchar_t* key_path,
                     const std::wstring& label,
                     const wchar_t* placeholder) {
  const std::wstring executable = ExecutablePath();
  if (executable.empty()) {
    return false;
  }
  HKEY key = nullptr;
  if (::RegCreateKeyExW(HKEY_CURRENT_USER, key_path, 0, nullptr, 0, KEY_WRITE,
                        nullptr, &key, nullptr) != ERROR_SUCCESS) {
    return false;
  }
  const std::wstring icon = L"\"" + executable + L"\",0";
  const bool values_ok = SetRegistryString(key, nullptr, label) &&
                         SetRegistryString(key, L"Icon", icon) &&
                         SetRegistryString(key, L"Position", L"top");
  ::RegCloseKey(key);
  if (!values_ok) {
    return false;
  }
  const std::wstring command_key_path =
      std::wstring(key_path) + L"\\command";
  HKEY command_key = nullptr;
  if (::RegCreateKeyExW(HKEY_CURRENT_USER, command_key_path.c_str(), 0, nullptr,
                        0, KEY_WRITE, nullptr, &command_key,
                        nullptr) != ERROR_SUCCESS) {
    return false;
  }
  const std::wstring command =
      L"\"" + executable + L"\" --add-folder \"" + placeholder + L"\"";
  const bool command_ok = SetRegistryString(command_key, nullptr, command);
  ::RegCloseKey(command_key);
  return command_ok;
}

bool CreateShellContextMenu() {
  // "添加到抽屉" / "添加当前文件夹到抽屉", written as escapes so the runner
  // source stays ASCII-only.
  const std::wstring folder_label =
      L"\u6DFB\u52A0\u5230\u62BD\u5C49";
  const std::wstring background_label =
      L"\u6DFB\u52A0\u5F53\u524D\u6587\u4EF6\u5939\u5230\u62BD\u5C49";
  const bool folder_ok = CreateMenuEntry(kShellMenuKey, folder_label, L"%1");
  const bool background_ok =
      CreateMenuEntry(kShellMenuBackgroundKey, background_label, L"%V");
  return folder_ok && background_ok;
}

}  // namespace

namespace native_shell {

std::wstring ShowFolderPicker(HWND owner) {
  IFileOpenDialog* dialog =
      CreateOpenDialog(owner, /*pick_folders=*/true, /*json_only=*/false, L"");
  if (dialog == nullptr) {
    return std::wstring();
  }
  IShellItem* item = nullptr;
  std::wstring result;
  if (SUCCEEDED(dialog->GetResult(&item))) {
    result = PathFromShellItem(item);
  }
  SafeRelease(&item);
  SafeRelease(&dialog);
  return result;
}

std::wstring ShowFilePicker(HWND owner, bool json_only) {
  IFileOpenDialog* dialog = CreateOpenDialog(
      owner, /*pick_folders=*/false, json_only, L"");
  if (dialog == nullptr) {
    return std::wstring();
  }
  IShellItem* item = nullptr;
  std::wstring result;
  if (SUCCEEDED(dialog->GetResult(&item))) {
    result = PathFromShellItem(item);
  }
  SafeRelease(&item);
  SafeRelease(&dialog);
  return result;
}

std::wstring ShowJsonSaveDialog(HWND owner,
                                const std::wstring& suggested_name) {
  IFileSaveDialog* dialog = nullptr;
  if (FAILED(::CoCreateInstance(CLSID_FileSaveDialog, nullptr,
                                CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&dialog)))) {
    return std::wstring();
  }
  DWORD options = 0;
  if (FAILED(dialog->GetOptions(&options))) {
    options = 0;
  }
  dialog->SetOptions(options | FOS_OVERWRITEPROMPT | FOS_FORCEFILESYSTEM |
                     FOS_PATHMUSTEXIST);
  const COMDLG_FILTERSPEC filters[] = {{L"JSON", L"*.json"}};
  dialog->SetFileTypes(1, filters);
  dialog->SetDefaultExtension(L"json");
  if (!suggested_name.empty()) {
    dialog->SetFileName(suggested_name.c_str());
  }
  IShellItem* item = nullptr;
  std::wstring result;
  if (SUCCEEDED(dialog->Show(owner)) && SUCCEEDED(dialog->GetResult(&item))) {
    result = PathFromShellItem(item);
  }
  SafeRelease(&item);
  SafeRelease(&dialog);
  return result;
}

std::wstring StartupShortcutPath() {
  PWSTR folder = nullptr;
  if (FAILED(::SHGetKnownFolderPath(FOLDERID_Startup, 0, nullptr, &folder)) ||
      folder == nullptr) {
    return std::wstring();
  }
  std::wstring path(folder);
  ::CoTaskMemFree(folder);
  path += L"\\\u62BD\u5C49.lnk";
  return path;
}

namespace {

// Phase 20: before the app was renamed the shortcut was "Resource Hub.lnk".
std::wstring LegacyStartupShortcutPath() {
  PWSTR folder = nullptr;
  if (FAILED(::SHGetKnownFolderPath(FOLDERID_Startup, 0, nullptr, &folder)) ||
      folder == nullptr) {
    return std::wstring();
  }
  std::wstring path(folder);
  ::CoTaskMemFree(folder);
  path += L"\\Resource Hub.lnk";
  return path;
}

}  // namespace

bool SetLaunchAtStartup(bool enabled) {
  const std::wstring shortcut = StartupShortcutPath();
  if (shortcut.empty()) {
    return false;
  }
  const std::wstring legacy = LegacyStartupShortcutPath();
  if (!enabled) {
    const bool removed_new = ::DeleteFileW(shortcut.c_str()) != 0 ||
                             ::GetLastError() == ERROR_FILE_NOT_FOUND;
    const bool removed_legacy =
        legacy.empty() || ::DeleteFileW(legacy.c_str()) != 0 ||
        ::GetLastError() == ERROR_FILE_NOT_FOUND;
    return removed_new && removed_legacy;
  }
  if (!legacy.empty()) {
    ::DeleteFileW(legacy.c_str());
  }

  const std::wstring executable = ExecutablePath();
  if (executable.empty()) {
    return false;
  }
  const size_t separator = executable.find_last_of(L"\\/");
  const std::wstring working_directory =
      separator == std::wstring::npos ? executable
                                      : executable.substr(0, separator);

  IShellLinkW* link = nullptr;
  if (FAILED(::CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER,
                                IID_PPV_ARGS(&link)))) {
    return false;
  }
  bool saved = false;
  if (SUCCEEDED(link->SetPath(executable.c_str())) &&
      SUCCEEDED(link->SetArguments(kStartupHiddenFlag)) &&
      SUCCEEDED(link->SetWorkingDirectory(working_directory.c_str())) &&
      SUCCEEDED(link->SetIconLocation(executable.c_str(), 0)) &&
      SUCCEEDED(link->SetDescription(L"\u62BD\u5C49 Drawer"))) {
    IPersistFile* file = nullptr;
    if (SUCCEEDED(link->QueryInterface(IID_PPV_ARGS(&file)))) {
      saved = SUCCEEDED(file->Save(shortcut.c_str(), TRUE));
      SafeRelease(&file);
    }
  }
  SafeRelease(&link);
  return saved;
}

bool GetLaunchAtStartup() {
  const std::wstring shortcut = StartupShortcutPath();
  return !shortcut.empty() &&
         ::GetFileAttributesW(shortcut.c_str()) != INVALID_FILE_ATTRIBUTES;
}

bool SetShellContextMenuEnabled(bool enabled) {
  if (enabled) {
    return CreateShellContextMenu();
  }
  bool removed = true;
  for (const wchar_t* key : {kShellMenuKey, kShellMenuBackgroundKey}) {
    const LONG result = ::RegDeleteTreeW(HKEY_CURRENT_USER, key);
    removed = removed &&
              (result == ERROR_SUCCESS || result == ERROR_FILE_NOT_FOUND);
  }
  return removed;
}

bool GetShellContextMenuEnabled() {
  HKEY key = nullptr;
  if (::RegOpenKeyExW(HKEY_CURRENT_USER, kShellMenuKey, 0, KEY_READ, &key) !=
      ERROR_SUCCESS) {
    return false;
  }
  ::RegCloseKey(key);
  return true;
}

bool OpenTarget(const std::wstring& target) {
  if (target.empty()) {
    return false;
  }
  // We are the foreground process here (the user just clicked in our window),
  // so we are allowed to hand the next SetForegroundWindow call to the shell.
  // Without this, Windows' foreground lock can create Explorer/the browser
  // behind this window even though the process is launched successfully.
  ::AllowSetForegroundWindow(ASFW_ANY);
  const HINSTANCE result = ::ShellExecuteW(nullptr, L"open", target.c_str(),
                                           nullptr, nullptr, SW_SHOWNORMAL);
  return reinterpret_cast<INT_PTR>(result) > 32;
}

bool RevealPath(const std::wstring& path) {
  if (path.empty()) {
    return false;
  }
  PIDLIST_ABSOLUTE item = nullptr;
  if (FAILED(::SHParseDisplayName(path.c_str(), nullptr, &item, 0, nullptr)) ||
      item == nullptr) {
    return false;
  }
  ::AllowSetForegroundWindow(ASFW_ANY);
  const HRESULT result = ::SHOpenFolderAndSelectItems(item, 0, nullptr, 0);
  ::CoTaskMemFree(item);
  return SUCCEEDED(result);
}

}  // namespace native_shell
