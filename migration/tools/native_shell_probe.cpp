// Direct probe for windows/runner/native_shell.cpp.
//
// The file dialogs and the Startup shortcut are pure Win32 and cannot be driven
// from widget tests, so this tiny console harness calls the same functions the
// Flutter runner calls and prints the observable result:
//
//   native-shell-probe.exe startup   create + verify + delete the .lnk
//   native-shell-probe.exe folder    open the folder picker, auto-close it
//   native-shell-probe.exe save      open the save dialog, auto-close it
//   native-shell-probe.exe open <path-or-url>    ShellExecute hand-off
//   native-shell-probe.exe reveal <path>         Explorer reveal hand-off
//
// Build (from the repository root, in a vcvars64 shell):
//   cl /nologo /EHsc /std:c++17 /I app\windows\runner ^
//      migration\tools\native_shell_probe.cpp app\windows\runner\native_shell.cpp ^
//      /link shell32.lib ole32.lib uuid.lib user32.lib ^
//      /OUT:build\native-shell-probe.exe

#include <windows.h>

#include <chrono>
#include <cstdio>
#include <cwchar>
#include <string>
#include <thread>

#include "native_shell.h"

namespace {

void CloseDialogSoon() {
  std::thread([]() {
    std::this_thread::sleep_for(std::chrono::milliseconds(1500));
    HWND dialog = ::FindWindowW(L"#32770", nullptr);
    std::wprintf(L"dialog_seen=%d\n", dialog != nullptr ? 1 : 0);
    std::fflush(stdout);
    if (dialog != nullptr) {
      // WM_CLOSE / WM_COMMAND on the dialog itself are ignored; the Cancel
      // button closes it reliably.
      HWND cancel = ::GetDlgItem(dialog, IDCANCEL);
      if (cancel != nullptr) {
        ::PostMessageW(cancel, BM_CLICK, 0, 0);
      } else {
        ::PostMessageW(dialog, WM_KEYDOWN, VK_ESCAPE, 0);
      }
    }
  }).detach();
}

void PrintPath(const wchar_t* label, const std::wstring& value) {
  std::wprintf(L"%ls=[%ls]\n", label, value.c_str());
  std::fflush(stdout);
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  ::SetConsoleOutputCP(CP_UTF8);
  ::CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);

  const std::wstring mode = argc > 1 ? argv[1] : L"startup";
  if (mode == L"startup") {
    PrintPath(L"shortcut_path", native_shell::StartupShortcutPath());
    const bool created = native_shell::SetLaunchAtStartup(true);
    std::wprintf(L"create=%d exists_after_create=%d\n", created ? 1 : 0,
                 native_shell::GetLaunchAtStartup() ? 1 : 0);
    const bool removed = native_shell::SetLaunchAtStartup(false);
    std::wprintf(L"remove=%d exists_after_remove=%d\n", removed ? 1 : 0,
                 native_shell::GetLaunchAtStartup() ? 1 : 0);
    std::fflush(stdout);
  } else if (mode == L"open" || mode == L"reveal") {
    if (argc < 3) {
      std::wprintf(L"missing target path\n");
      return 2;
    }
    const std::wstring target = argv[2];
    if (mode == L"open") {
      const bool ok = native_shell::OpenTarget(target);
      std::wprintf(L"open=%d target=%ls\n", ok ? 1 : 0, target.c_str());
    } else {
      const bool ok = native_shell::RevealPath(target);
      std::wprintf(L"reveal=%d target=%ls\n", ok ? 1 : 0, target.c_str());
    }
    std::fflush(stdout);
  } else if (mode == L"folder") {
    CloseDialogSoon();
    PrintPath(L"picked_folder", native_shell::ShowFolderPicker(nullptr));
  } else if (mode == L"save") {
    CloseDialogSoon();
    PrintPath(L"saved_path", native_shell::ShowJsonSaveDialog(nullptr, L"probe.json"));
  } else {
    std::wprintf(L"unknown mode: %ls\n", mode.c_str());
    return 2;
  }

  ::CoUninitialize();
  return 0;
}
