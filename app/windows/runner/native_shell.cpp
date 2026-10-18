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
  path += L"\\Resource Hub.lnk";
  return path;
}

bool SetLaunchAtStartup(bool enabled) {
  const std::wstring shortcut = StartupShortcutPath();
  if (shortcut.empty()) {
    return false;
  }
  if (!enabled) {
    if (::DeleteFileW(shortcut.c_str())) {
      return true;
    }
    return ::GetLastError() == ERROR_FILE_NOT_FOUND;
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
      SUCCEEDED(link->SetDescription(L"Resource Hub"))) {
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
