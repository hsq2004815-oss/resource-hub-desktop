#include <flutter/dart_project.h>
#include <flutter/flutter_view_controller.h>
#include <shellapi.h>
#include <windows.h>

#include <string>

#include "flutter_window.h"
#include "utils.h"
#include "window_messages.h"

int APIENTRY wWinMain(_In_ HINSTANCE instance, _In_opt_ HINSTANCE prev,
                      _In_ wchar_t *command_line, _In_ int show_command) {
  // Attach to console when present (e.g., 'flutter run') or create a
  // new console when running with a debugger.
  if (!::AttachConsole(ATTACH_PARENT_PROCESS) && ::IsDebuggerPresent()) {
    CreateAndAttachConsole();
  }

  // Initialize COM, so that it is available for use in the library and/or
  // plugins.
  ::CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);

  // The Explorer context-menu entry passes the selected folder after the flag.
  std::wstring add_folder;
  {
    int argc = 0;
    wchar_t** argv = ::CommandLineToArgvW(::GetCommandLineW(), &argc);
    if (argv != nullptr) {
      for (int i = 1; i + 1 < argc; ++i) {
        if (::wcscmp(argv[i], kAddFolderFlag) == 0) {
          add_folder = argv[i + 1];
          break;
        }
      }
      ::LocalFree(argv);
    }
  }

  // Single instance: the second launch only wakes the window that already
  // exists. Without this the two instances would spawn two backends that fight
  // over the same global hotkey and data files.
  HANDLE instance_mutex = ::CreateMutexW(
      nullptr, TRUE, L"Local\\Mytools.ResourceHub.Flutter");
  if (instance_mutex != nullptr && ::GetLastError() == ERROR_ALREADY_EXISTS) {
    const UINT wake_message = ::RegisterWindowMessageW(kShowWindowMessageName);
    if (HWND existing =
            ::FindWindowW(L"FLUTTER_RUNNER_WIN32_WINDOW", nullptr)) {
      // Phase 19: hand the folder to the running instance before waking it, so
      // the add is processed even while the window is hidden in the tray.
      if (!add_folder.empty()) {
        COPYDATASTRUCT payload = {};
        payload.dwData = kAddFolderCopyData;
        payload.cbData =
            static_cast<DWORD>((add_folder.size() + 1) * sizeof(wchar_t));
        payload.lpData = const_cast<wchar_t*>(add_folder.c_str());
        DWORD_PTR ignored_result = 0;
        ::SendMessageTimeoutW(existing, WM_COPYDATA, 0,
                              reinterpret_cast<LPARAM>(&payload),
                              SMTO_ABORTIFHUNG | SMTO_BLOCK, 3000,
                              &ignored_result);
      }
      ::PostMessageW(existing, wake_message, 0, 0);
    }
    ::CloseHandle(instance_mutex);
    ::CoUninitialize();
    return EXIT_SUCCESS;
  }

  flutter::DartProject project(L"data");

  std::vector<std::string> command_line_arguments =
      GetCommandLineArguments();

  project.set_dart_entrypoint_arguments(std::move(command_line_arguments));

  FlutterWindow window(project);
  Win32Window::Point origin(10, 10);
  // Client area 1280x820, matching the original Tkinter geometry("1280x820").
  Win32Window::Size size(1280, 820);
  // Window title: "抽屉 / Drawer" written as escapes so the runner stays
  // ASCII-only; Flutter replaces it with the localized name after boot.
  if (!window.Create(L"\u62BD\u5C49", origin, size)) {
    return EXIT_FAILURE;
  }
  window.SetQuitOnClose(true);

  ::MSG msg;
  while (::GetMessage(&msg, nullptr, 0, 0)) {
    ::TranslateMessage(&msg);
    ::DispatchMessage(&msg);
  }

  ::CoUninitialize();
  if (instance_mutex != nullptr) {
    ::CloseHandle(instance_mutex);
  }
  return EXIT_SUCCESS;
}
