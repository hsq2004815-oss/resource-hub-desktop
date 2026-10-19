#include "flutter_window.h"

#include <dwmapi.h>
#include <flutter/standard_method_codec.h>
#include <shellapi.h>

#include <optional>
#include <string>
#include <vector>

#include "flutter/generated_plugin_registrant.h"
#include "native_shell.h"
#include "resource.h"
#include "utils.h"
#include "window_messages.h"

// Windows 11 corner-rounding attribute (DWMWA_WINDOW_CORNER_PREFERENCE). Kept as
// a local constant so the runner also builds against older Windows SDKs.
constexpr DWORD kDwmWindowCornerPreference = 33;
constexpr int kDwmCornerRound = 2;    // DWMWCP_ROUND
constexpr int kDwmCornerDefault = 0;  // DWMWCP_DEFAULT

namespace {

// Tray icon plumbing.
constexpr UINT kTrayCallbackMessage = WM_APP + 1;
constexpr UINT kTrayIconId = 1;
constexpr UINT kMenuToggle = 1001;
constexpr UINT kMenuExit = 1002;

// Posted by a second instance to wake the window that already exists.
const UINT kWakeMessage = ::RegisterWindowMessageW(kShowWindowMessageName);

// Posted right after a quick-panel activation hand-off: clears
// quick_activation_settling_ once the WM_ACTIVATE traffic caused by
// ForceForeground() has been processed.
constexpr UINT kQuickActivationSettled = WM_APP + 78;

// While the HUD is open, poll the system foreground window. The AttachThreadInput
// hand-off used by ForceForeground() does not always deliver
// WM_ACTIVATE(WA_INACTIVE) to the top-level window, so the first click outside
// could otherwise be ignored until the panel was clicked once (Phase 18.2).
constexpr UINT_PTR kQuickForegroundTimerId = 0x5251;
constexpr UINT kQuickForegroundTimerIntervalMs = 100;

// Property key used to find the FlutterWindow instance from the subclassed
// Flutter view window procedure.
constexpr wchar_t kChildWindowProp[] = L"ResourceHubFlutterWindow";

// utils.h only ships UTF-16 -> UTF-8; the channels need the other way.
std::wstring Utf16FromUtf8(const std::string& utf8) {
  if (utf8.empty()) {
    return std::wstring();
  }
  const int length = static_cast<int>(utf8.size());
  const int size =
      ::MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), length, nullptr, 0);
  if (size <= 0) {
    return std::wstring();
  }
  std::wstring result(static_cast<size_t>(size), L'\0');
  ::MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), length, result.data(), size);
  return result;
}

bool HasCommandLineFlag(const wchar_t* flag) {
  const std::wstring command_line = ::GetCommandLineW();
  return command_line.find(flag) != std::wstring::npos;
}

// Phase 19: value after `--add-folder`, or an empty string.
std::wstring FindAddFolderArgument() {
  int argc = 0;
  wchar_t** argv = ::CommandLineToArgvW(::GetCommandLineW(), &argc);
  std::wstring result;
  if (argv != nullptr) {
    for (int i = 1; i + 1 < argc; ++i) {
      if (::wcscmp(argv[i], kAddFolderFlag) == 0) {
        result = argv[i + 1];
        break;
      }
    }
    ::LocalFree(argv);
  }
  return result;
}

// Reads an integer field from a map argument; returns |fallback| if absent.
int MapInt(const flutter::EncodableMap& map, const char* key, int fallback) {
  auto it = map.find(flutter::EncodableValue(key));
  if (it == map.end()) {
    return fallback;
  }
  if (const auto* value = std::get_if<int32_t>(&it->second)) {
    return *value;
  }
  if (const auto* value = std::get_if<int64_t>(&it->second)) {
    return static_cast<int>(*value);
  }
  if (const auto* value = std::get_if<double>(&it->second)) {
    return static_cast<int>(*value);
  }
  return fallback;
}

// Reads a UTF-8 string field from a map argument; returns |fallback| if absent.
std::wstring MapString(const flutter::EncodableMap& map,
                       const char* key,
                       const std::wstring& fallback) {
  auto it = map.find(flutter::EncodableValue(key));
  if (it == map.end()) {
    return fallback;
  }
  const auto* value = std::get_if<std::string>(&it->second);
  if (value == nullptr) {
    return fallback;
  }
  return Utf16FromUtf8(*value);
}

}  // namespace

FlutterWindow::FlutterWindow(const flutter::DartProject& project)
    : project_(project) {
  pending_add_folder_ = FindAddFolderArgument();
}

FlutterWindow::~FlutterWindow() {}

bool FlutterWindow::OnCreate() {
  if (!Win32Window::OnCreate()) {
    return false;
  }

  RECT frame = GetClientArea();

  // The size here must match the window dimensions to avoid unnecessary surface
  // creation / destruction in the startup path.
  flutter_controller_ = std::make_unique<flutter::FlutterViewController>(
      frame.right - frame.left, frame.bottom - frame.top, project_);
  // Ensure that basic setup of the controller was successful.
  if (!flutter_controller_->engine() || !flutter_controller_->view()) {
    return false;
  }
  RegisterPlugins(flutter_controller_->engine());
  SetChildContent(flutter_controller_->view()->GetNativeWindow());

  // Drag & drop: the Flutter view covers the client area, so Explorer's drop
  // lands on the view window, not on the top-level one. Both accept files, and
  // the view is subclassed so its WM_DROPFILES reaches this class.
  ::DragAcceptFiles(GetHandle(), TRUE);
  if (HWND child = ::GetWindow(GetHandle(), GW_CHILD)) {
    AttachDropTarget(child);
  }

  RegisterChannels();
  InstallTray();

  // A sign-in launch (Startup shortcut) starts hidden in the tray; the user gets
  // to it through the tray icon or the global hotkey.
  startup_hidden_ = HasCommandLineFlag(kStartupHiddenFlag);
  if (!startup_hidden_) {
    flutter_controller_->engine()->SetNextFrameCallback([&]() {
      this->Show();
    });

    // Flutter can complete the first frame before the "show window" callback is
    // registered. The following call ensures a frame is pending to ensure the
    // window is shown. It is a no-op if the first frame hasn't completed yet.
    flutter_controller_->ForceRedraw();
  }

  return true;
}

void FlutterWindow::RegisterChannels() {
  window_channel_ =
      std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
          flutter_controller_->engine()->messenger(), "resource_hub/window",
          &flutter::StandardMethodCodec::GetInstance());
  window_channel_->SetMethodCallHandler(
      [this](const flutter::MethodCall<flutter::EncodableValue>& call,
             std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>>
                 result) {
        const std::string& method = call.method_name();

        if (method == "setTitle") {
          const auto* title = std::get_if<std::string>(call.arguments());
          if (title == nullptr) {
            result->Error("bad_args", "setTitle expects a UTF-8 string");
            return;
          }
          SetWindowTextW(GetHandle(), Utf16FromUtf8(*title).c_str());
          result->Success();
          return;
        }

        if (method == "setTrayLabels") {
          const auto* args =
              std::get_if<flutter::EncodableMap>(call.arguments());
          if (args == nullptr) {
            result->Error("bad_args", "setTrayLabels expects a map");
            return;
          }
          tray_toggle_label_ = MapString(*args, "toggle", tray_toggle_label_);
          tray_exit_label_ = MapString(*args, "exit", tray_exit_label_);
          result->Success();
          return;
        }

        if (method == "hide") {
          HideToTray();
          result->Success(flutter::EncodableValue(false));
          return;
        }
        if (method == "show") {
          ShowFromTray();
          result->Success(flutter::EncodableValue(true));
          return;
        }
        if (method == "toggle") {
          ToggleVisibility();
          result->Success(flutter::EncodableValue(IsWindowVisibleNow()));
          return;
        }
        if (method == "isVisible") {
          result->Success(flutter::EncodableValue(IsWindowVisibleNow()));
          return;
        }
        if (method == "quit") {
          RequestQuit();
          result->Success();
          return;
        }

        // -- quick panel (Phase 16) ---------------------------------------
        if (method == "enterQuickMode") {
          int width = 480;
          int height = 600;
          if (const auto* args =
                  std::get_if<flutter::EncodableMap>(call.arguments())) {
            width = MapInt(*args, "width", width);
            height = MapInt(*args, "height", height);
          }
          result->Success(
              flutter::EncodableValue(EnterQuickMode(width, height)));
          return;
        }
        if (method == "exitQuickMode") {
          int visibility = 0;
          if (const auto* args =
                  std::get_if<flutter::EncodableMap>(call.arguments())) {
            const std::wstring value =
                MapString(*args, "visibility", L"auto");
            if (value == L"show") {
              visibility = 1;
            } else if (value == L"hide") {
              visibility = 2;
            }
          }
          ExitQuickMode(visibility);
          result->Success(flutter::EncodableValue(true));
          return;
        }
        if (method == "isQuickMode") {
          result->Success(flutter::EncodableValue(quick_mode_));
          return;
        }

        // -- shell dialogs ------------------------------------------------
        if (method == "pickFolder") {
          const std::wstring path = native_shell::ShowFolderPicker(GetHandle());
          result->Success(path.empty()
                              ? flutter::EncodableValue()
                              : flutter::EncodableValue(Utf8FromUtf16(path.c_str())));
          return;
        }
        if (method == "pickFile") {
          const std::wstring path = native_shell::ShowFilePicker(
              GetHandle(), /*json_only=*/false);
          result->Success(path.empty()
                              ? flutter::EncodableValue()
                              : flutter::EncodableValue(Utf8FromUtf16(path.c_str())));
          return;
        }
        if (method == "pickJsonFile") {
          const std::wstring path = native_shell::ShowFilePicker(
              GetHandle(), /*json_only=*/true);
          result->Success(path.empty()
                              ? flutter::EncodableValue()
                              : flutter::EncodableValue(Utf8FromUtf16(path.c_str())));
          return;
        }
        if (method == "saveFile") {
          std::wstring suggested_name;
          if (const auto* args =
                  std::get_if<flutter::EncodableMap>(call.arguments())) {
            suggested_name = MapString(*args, "suggestedName", suggested_name);
          }
          const std::wstring path =
              native_shell::ShowJsonSaveDialog(GetHandle(), suggested_name);
          result->Success(path.empty()
                              ? flutter::EncodableValue()
                              : flutter::EncodableValue(Utf8FromUtf16(path.c_str())));
          return;
        }

        // -- launch at startup --------------------------------------------
        if (method == "setLaunchAtStartup") {
          const auto* enabled = std::get_if<bool>(call.arguments());
          if (enabled == nullptr) {
            result->Error("bad_args", "setLaunchAtStartup expects a bool");
            return;
          }
          const bool applied = native_shell::SetLaunchAtStartup(*enabled);
          result->Success(flutter::EncodableValue(applied));
          return;
        }
        if (method == "isLaunchAtStartup") {
          result->Success(
              flutter::EncodableValue(native_shell::GetLaunchAtStartup()));
          return;
        }

        // -- Phase 19: Explorer context menu -------------------------------
        if (method == "shellAddReady") {
          shell_add_ready_ = true;
          if (window_channel_ && !pending_add_folder_.empty()) {
            const std::wstring path = pending_add_folder_;
            pending_add_folder_.clear();
            window_channel_->InvokeMethod(
                "addFolderPath",
                std::make_unique<flutter::EncodableValue>(
                    Utf8FromUtf16(path.c_str())));
          }
          result->Success();
          return;
        }
        if (method == "setShellContextMenuEnabled") {
          const auto* enabled = std::get_if<bool>(call.arguments());
          if (enabled == nullptr) {
            result->Error("bad_args",
                          "setShellContextMenuEnabled expects a bool");
            return;
          }
          result->Success(flutter::EncodableValue(
              native_shell::SetShellContextMenuEnabled(*enabled)));
          return;
        }
        if (method == "isShellContextMenuEnabled") {
          result->Success(flutter::EncodableValue(
              native_shell::GetShellContextMenuEnabled()));
          return;
        }

        // -- open / reveal external targets -------------------------------
        // Done here (not in the Python backend) because only the process that
        // owns the foreground window may hand foreground rights to Explorer or
        // the browser; otherwise those windows open behind this one.
        if (method == "openTarget") {
          const auto* target = std::get_if<std::string>(call.arguments());
          if (target == nullptr) {
            result->Error("bad_args", "openTarget expects a UTF-8 string");
            return;
          }
          result->Success(flutter::EncodableValue(
              native_shell::OpenTarget(Utf16FromUtf8(*target))));
          return;
        }
        if (method == "revealPath") {
          const auto* target = std::get_if<std::string>(call.arguments());
          if (target == nullptr) {
            result->Error("bad_args", "revealPath expects a UTF-8 string");
            return;
          }
          result->Success(flutter::EncodableValue(
              native_shell::RevealPath(Utf16FromUtf8(*target))));
          return;
        }

        result->NotImplemented();
      });
}

void FlutterWindow::InstallTray() {
  NOTIFYICONDATAW data = {};
  data.cbSize = sizeof(data);
  data.hWnd = GetHandle();
  data.uID = kTrayIconId;
  data.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
  data.uCallbackMessage = kTrayCallbackMessage;
  data.hIcon = static_cast<HICON>(
      ::LoadImageW(::GetModuleHandle(nullptr), MAKEINTRESOURCEW(IDI_APP_ICON),
                   IMAGE_ICON, ::GetSystemMetrics(SM_CXSMICON),
                   ::GetSystemMetrics(SM_CYSMICON), LR_DEFAULTCOLOR));
  if (data.hIcon == nullptr) {
    data.hIcon = ::LoadIconW(nullptr, IDI_APPLICATION);
  }
  wcscpy_s(data.szTip, L"\u62BD\u5C49 Drawer");
  tray_installed_ = ::Shell_NotifyIconW(NIM_ADD, &data) != FALSE;
}

void FlutterWindow::RemoveTray() {
  if (!tray_installed_) {
    return;
  }
  NOTIFYICONDATAW data = {};
  data.cbSize = sizeof(data);
  data.hWnd = GetHandle();
  data.uID = kTrayIconId;
  ::Shell_NotifyIconW(NIM_DELETE, &data);
  tray_installed_ = false;
}

void FlutterWindow::ShowTrayMenu() {
  POINT cursor;
  ::GetCursorPos(&cursor);
  HMENU menu = ::CreatePopupMenu();
  if (menu == nullptr) {
    return;
  }
  ::AppendMenuW(menu, MF_STRING, kMenuToggle, tray_toggle_label_.c_str());
  ::AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
  ::AppendMenuW(menu, MF_STRING, kMenuExit, tray_exit_label_.c_str());

  // Required, otherwise the menu does not close when the user clicks elsewhere.
  ::SetForegroundWindow(GetHandle());
  ::TrackPopupMenu(menu, TPM_BOTTOMALIGN | TPM_LEFTALIGN, cursor.x, cursor.y, 0,
                   GetHandle(), nullptr);
  ::PostMessageW(GetHandle(), WM_NULL, 0, 0);
  ::DestroyMenu(menu);
}

bool FlutterWindow::IsWindowVisibleNow() {
  return ::IsWindowVisible(GetHandle()) != FALSE;
}

void FlutterWindow::HideToTray() {
  if (!tray_installed_) {
    // Without a tray icon the window would become unreachable.
    RequestQuit();
    return;
  }
  ::ShowWindow(GetHandle(), SW_HIDE);
}

void FlutterWindow::ShowFromTray() {
  ::ShowWindow(GetHandle(), SW_RESTORE);
  ::ShowWindow(GetHandle(), SW_SHOW);
  ForceForeground();
}

void FlutterWindow::ForceForeground() {
  HWND handle = GetHandle();
  if (handle == nullptr) {
    return;
  }
  // Windows refuses SetForegroundWindow from a background process; briefly
  // becoming topmost is the trick the legacy app used (resource_hub.pyw:1437).
  ::SetWindowPos(handle, HWND_TOPMOST, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE);
  ::SetWindowPos(handle, HWND_NOTOPMOST, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE);
  ::SetForegroundWindow(handle);
  if (::GetForegroundWindow() != handle) {
    // The global hotkey is owned by the backend process, so this process has no
    // foreground rights. Attaching to the current foreground thread's input
    // queue is the standard workaround and makes the hotkey panel really active
    // (so Esc/typing work and clicking anywhere else fires WM_ACTIVATE).
    const HWND foreground = ::GetForegroundWindow();
    const DWORD foreground_thread =
        foreground != nullptr ? ::GetWindowThreadProcessId(foreground, nullptr)
                              : 0;
    const DWORD this_thread = ::GetCurrentThreadId();
    if (foreground_thread != 0 && foreground_thread != this_thread) {
      ::AttachThreadInput(this_thread, foreground_thread, TRUE);
      ::SetForegroundWindow(handle);
      ::AttachThreadInput(this_thread, foreground_thread, FALSE);
    }
  }
  HWND child = ::GetWindow(handle, GW_CHILD);
  if (child != nullptr) {
    ::SetFocus(child);
  }
}

void FlutterWindow::ToggleVisibility() {
  if (quick_mode_) {
    // Tray click / wake message while the HUD is up: close the HUD and return to
    // the pre-quick window state. Dart restores its layout from the notification.
    NotifyQuickDismissed();
    ExitQuickMode();
    return;
  }
  if (IsWindowVisibleNow()) {
    HideToTray();
  } else {
    ShowFromTray();
  }
}

bool FlutterWindow::EnterQuickMode(int logical_width, int logical_height) {
  HWND handle = GetHandle();
  if (handle == nullptr) {
    return false;
  }
  if (quick_mode_) {
    return true;
  }
  quick_was_visible_ = IsWindowVisibleNow();
  // A minimized window would otherwise save a bogus (off-screen) rect.
  if (::IsIconic(handle)) {
    ::ShowWindow(handle, SW_RESTORE);
  }
  // ...and a maximized window ignores SetWindowPos sizing: the HUD request
  // would be applied to the restore rect instead of 480x600 logical, opening a
  // full-size panel (Phase 24). Restore it first and remember the state.
  quick_saved_maximized_ = ::IsZoomed(handle) != FALSE;
  if (quick_saved_maximized_) {
    ::ShowWindow(handle, SW_RESTORE);
  }
  if (!::GetWindowRect(handle, &quick_saved_rect_)) {
    return false;
  }
  quick_saved_style_ = ::GetWindowLongPtrW(handle, GWL_STYLE);
  quick_saved_ex_style_ = ::GetWindowLongPtrW(handle, GWL_EXSTYLE);

  // Flutter passes logical pixels; scale to the window's monitor DPI.
  UINT dpi = ::GetDpiForWindow(handle);
  if (dpi == 0) {
    dpi = 96;
  }
  const int width = ::MulDiv(logical_width, static_cast<int>(dpi), 96);
  const int height = ::MulDiv(logical_height, static_cast<int>(dpi), 96);

  // Spotlight-style placement: horizontally centred on the monitor under the
  // cursor, a little above the vertical centre.
  POINT cursor = {};
  ::GetCursorPos(&cursor);
  const HMONITOR monitor = ::MonitorFromPoint(cursor, MONITOR_DEFAULTTONEAREST);
  MONITORINFO info = {};
  info.cbSize = sizeof(info);
  int x = quick_saved_rect_.left;
  int y = quick_saved_rect_.top;
  if (::GetMonitorInfoW(monitor, &info)) {
    const RECT work = info.rcWork;
    x = work.left + ((work.right - work.left) - width) / 2;
    y = work.top + ((work.bottom - work.top) * 12) / 100;
  }

  LONG_PTR style = quick_saved_style_ & ~(WS_CAPTION | WS_THICKFRAME |
                                          WS_MINIMIZEBOX | WS_MAXIMIZEBOX |
                                          WS_SYSMENU);
  style |= WS_POPUP;
  ::SetWindowLongPtrW(handle, GWL_STYLE, style);
  ::SetWindowLongPtrW(handle, GWL_EXSTYLE,
                      (quick_saved_ex_style_ & ~WS_EX_APPWINDOW) |
                          WS_EX_TOOLWINDOW);
  const int corner = kDwmCornerRound;
  ::DwmSetWindowAttribute(handle, kDwmWindowCornerPreference,
                          &corner, sizeof(corner));

  quick_mode_ = true;
  quick_dismiss_posted_ = false;
  quick_activation_settling_ = true;
  ::SetWindowPos(handle, HWND_TOPMOST, x, y, width, height,
                 SWP_FRAMECHANGED | SWP_SHOWWINDOW);
  ::ShowWindow(handle, SW_SHOWNORMAL);
  // The Python backend owns the hotkey, so this process has no foreground
  // rights; ForceForeground() takes them explicitly so the panel receives
  // Esc/typing and a click anywhere else produces WM_ACTIVATE(WA_INACTIVE).
  ForceForeground();
  // Stay above normal windows again after the helper's topmost round-trip.
  ::SetWindowPos(handle, HWND_TOPMOST, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
  // Forcing the foreground produces a transient WA_INACTIVE; only accept
  // dismissal after that activation traffic has been drained.
  ::PostMessageW(handle, kQuickActivationSettled, 0, 0);
  quick_had_foreground_ = false;
  StartQuickForegroundWatch();
  return true;
}

void FlutterWindow::ExitQuickMode(int visibility) {
  HWND handle = GetHandle();
  if (handle == nullptr || !quick_mode_) {
    return;
  }
  const bool was_visible = quick_was_visible_;
  const bool show_window =
      visibility == 1 || (visibility == 0 && was_visible);
  quick_mode_ = false;
  quick_dismiss_posted_ = false;
  quick_activation_settling_ = false;
  quick_had_foreground_ = false;
  StopQuickForegroundWatch();
  // Hide before restoring the frame when the window is going away: otherwise the
  // HUD-sized window briefly grows back on screen while Flutter still displays
  // the previous frame, leaving black margins around a stale tree (Phase 16 QA).
  if (!show_window) {
    ::ShowWindow(handle, SW_HIDE);
  }
  ::SetWindowLongPtrW(handle, GWL_STYLE, quick_saved_style_);
  ::SetWindowLongPtrW(handle, GWL_EXSTYLE, quick_saved_ex_style_);
  const int corner = kDwmCornerDefault;
  ::DwmSetWindowAttribute(handle, kDwmWindowCornerPreference,
                          &corner, sizeof(corner));
  ::SetWindowPos(handle, HWND_NOTOPMOST, quick_saved_rect_.left,
                 quick_saved_rect_.top,
                 quick_saved_rect_.right - quick_saved_rect_.left,
                 quick_saved_rect_.bottom - quick_saved_rect_.top,
                 SWP_FRAMECHANGED | SWP_NOACTIVATE);
  if (show_window) {
    // Do not steal the foreground on the automatic path: the user likely
    // clicked another window and that is exactly why the HUD is closing.
    if (quick_saved_maximized_) {
      // The user had the main window maximized before opening the HUD; put it
      // back the way they left it.
      ::ShowWindow(handle, SW_SHOWMAXIMIZED);
    } else {
      ::ShowWindow(handle, SW_RESTORE);
      ::ShowWindow(handle, SW_SHOW);
    }
    if (visibility == 1) {
      ForceForeground();
    }
  }
  // Ask the engine for a fresh frame right after the resize instead of waiting
  // for the next incidental invalidation.
  if (flutter_controller_) {
    flutter_controller_->ForceRedraw();
  }
}

void FlutterWindow::NotifyQuickDismissed() {
  if (!window_channel_ || !quick_mode_ || quick_dismiss_posted_) {
    return;
  }
  // One notification per quick session; Dart restores its UI and calls
  // exitQuickMode(), which clears the flag.
  quick_dismiss_posted_ = true;
  window_channel_->InvokeMethod("quickDismissed", nullptr);
}

void FlutterWindow::HandleAddFolderRequest(const std::wstring& path) {
  if (!shell_add_ready_ || !window_channel_) {
    pending_add_folder_ = path;
    return;
  }
  window_channel_->InvokeMethod(
      "addFolderPath",
      std::make_unique<flutter::EncodableValue>(Utf8FromUtf16(path.c_str())));
}

void FlutterWindow::StartQuickForegroundWatch() {
  HWND handle = GetHandle();
  if (handle == nullptr) {
    return;
  }
  ::SetTimer(handle, kQuickForegroundTimerId, kQuickForegroundTimerIntervalMs,
             nullptr);
}

void FlutterWindow::StopQuickForegroundWatch() {
  HWND handle = GetHandle();
  if (handle != nullptr) {
    ::KillTimer(handle, kQuickForegroundTimerId);
  }
}

void FlutterWindow::CheckQuickForeground() {
  if (!quick_mode_ || quick_activation_settling_ || quick_dismiss_posted_) {
    return;
  }
  const HWND foreground = ::GetForegroundWindow();
  if (foreground == nullptr) {
    return;
  }
  DWORD foreground_pid = 0;
  ::GetWindowThreadProcessId(foreground, &foreground_pid);
  if (foreground_pid == ::GetCurrentProcessId()) {
    // The HUD (or its Flutter view) owns the foreground: a later switch to any
    // other process is a click-away.
    quick_had_foreground_ = true;
    return;
  }
  if (quick_had_foreground_) {
    NotifyQuickDismissed();
  }
}

void FlutterWindow::RequestQuit() {
  if (quitting_) {
    return;
  }
  quitting_ = true;
  RemoveTray();
  Destroy();
}

void FlutterWindow::PublishDroppedPaths(
    const std::vector<std::string>& paths) {
  if (!window_channel_ || paths.empty()) {
    return;
  }
  flutter::EncodableList list;
  list.reserve(paths.size());
  for (const std::string& path : paths) {
    list.emplace_back(path);
  }
  window_channel_->InvokeMethod(
      "dropPaths", std::make_unique<flutter::EncodableValue>(list));
}

void FlutterWindow::HandleDroppedFiles(HDROP drop) {
  const UINT count = ::DragQueryFileW(drop, 0xFFFFFFFF, nullptr, 0);
  std::vector<std::string> paths;
  paths.reserve(count);
  for (UINT index = 0; index < count; ++index) {
    const UINT length = ::DragQueryFileW(drop, index, nullptr, 0);
    if (length == 0) {
      continue;
    }
    std::wstring buffer(static_cast<size_t>(length) + 1, L'\0');
    if (::DragQueryFileW(drop, index, buffer.data(), length + 1) == 0) {
      continue;
    }
    buffer.resize(length);
    paths.push_back(Utf8FromUtf16(buffer.c_str()));
  }
  ::DragFinish(drop);
  PublishDroppedPaths(paths);
}

void FlutterWindow::AttachDropTarget(HWND child) {
  if (child == nullptr || child == child_window_) {
    return;
  }
  // The engine can recreate the view window (e.g. after a DPI change); detach
  // the previous one before subclassing the new one.
  if (child_window_ != nullptr && child_original_proc_ != nullptr &&
      ::IsWindow(child_window_)) {
    ::RemovePropW(child_window_, kChildWindowProp);
    ::SetWindowLongPtrW(child_window_, GWLP_WNDPROC,
                        reinterpret_cast<LONG_PTR>(child_original_proc_));
  }
  child_window_ = child;
  child_original_proc_ = reinterpret_cast<WNDPROC>(::SetWindowLongPtrW(
      child, GWLP_WNDPROC,
      reinterpret_cast<LONG_PTR>(&FlutterWindow::ChildWndProc)));
  ::SetPropW(child, kChildWindowProp, reinterpret_cast<HANDLE>(this));
  ::DragAcceptFiles(child, TRUE);
}

// static
LRESULT CALLBACK FlutterWindow::ChildWndProc(HWND window, UINT const message,
                                             WPARAM const wparam,
                                             LPARAM const lparam) noexcept {
  auto* that = reinterpret_cast<FlutterWindow*>(
      ::GetPropW(window, kChildWindowProp));
  if (that == nullptr) {
    return ::DefWindowProcW(window, message, wparam, lparam);
  }
  if (message == WM_DROPFILES) {
    that->HandleDroppedFiles(reinterpret_cast<HDROP>(wparam));
    return 0;
  }
  const WNDPROC original = that->child_original_proc_ != nullptr
                               ? that->child_original_proc_
                               : ::DefWindowProcW;
  if (message == WM_NCDESTROY) {
    ::RemovePropW(window, kChildWindowProp);
    that->child_window_ = nullptr;
    that->child_original_proc_ = nullptr;
  }
  return ::CallWindowProcW(original, window, message, wparam, lparam);
}

void FlutterWindow::OnDestroy() {
  if (child_window_ != nullptr && ::IsWindow(child_window_)) {
    ::DragAcceptFiles(child_window_, FALSE);
    if (child_original_proc_ != nullptr) {
      ::RemovePropW(child_window_, kChildWindowProp);
      ::SetWindowLongPtrW(child_window_, GWLP_WNDPROC,
                          reinterpret_cast<LONG_PTR>(child_original_proc_));
    }
  }
  child_window_ = nullptr;
  child_original_proc_ = nullptr;

  // By the time OnDestroy runs from WM_DESTROY the handle is already cleared;
  // the OS drops the drop-target registration with the window.
  if (HWND handle = GetHandle()) {
    ::DragAcceptFiles(handle, FALSE);
  }
  RemoveTray();
  if (flutter_controller_) {
    flutter_controller_ = nullptr;
  }

  Win32Window::OnDestroy();
}

LRESULT
FlutterWindow::MessageHandler(HWND hwnd, UINT const message,
                              WPARAM const wparam,
                              LPARAM const lparam) noexcept {
  // Phase 19: a second instance forwards an Explorer folder here.
  if (message == WM_COPYDATA) {
    const auto* data = reinterpret_cast<const COPYDATASTRUCT*>(lparam);
    if (data != nullptr && data->dwData == kAddFolderCopyData &&
        data->lpData != nullptr &&
        data->cbData >= static_cast<DWORD>(sizeof(wchar_t))) {
      const size_t count =
          static_cast<size_t>(data->cbData) / sizeof(wchar_t);
      std::wstring path(static_cast<const wchar_t*>(data->lpData), count);
      while (!path.empty() && path.back() == L'\0') {
        path.pop_back();
      }
      if (!path.empty()) {
        HandleAddFolderRequest(path);
        return TRUE;
      }
    }
    return FALSE;
  }

  // A second launch asks the running instance to come to the front.
  if (message == kWakeMessage) {
    if (quick_mode_) {
      NotifyQuickDismissed();
      ExitQuickMode();
    }
    ShowFromTray();
    return 0;
  }

  // The quick panel is a "click-away to dismiss" overlay: losing activation (the
  // user clicked another app, the desktop, or a browser opened by the panel)
  // closes it. Dart decides whether the window should stay visible afterwards.
  // Forcing the foreground for the quick panel briefly produces
  // WM_ACTIVATE(WA_INACTIVE) traffic; ignore dismissal until the posted
  // "settled" message arrives.
  if (quick_mode_ && message == WM_TIMER &&
      wparam == kQuickForegroundTimerId) {
    CheckQuickForeground();
    return 0;
  }
  if (quick_mode_ && message == WM_ACTIVATE &&
      LOWORD(wparam) == WA_INACTIVE) {
    if (!quick_activation_settling_) {
      NotifyQuickDismissed();
    }
    return 0;
  }
  if (message == kQuickActivationSettled) {
    quick_activation_settling_ = false;
    return 0;
  }

  // The engine may recreate the Flutter view window (e.g. after a DPI change);
  // keep the drop target attached to whatever child currently covers the client
  // area, otherwise only drops on the title bar/border would work.
  if (HWND handle = GetHandle()) {
    AttachDropTarget(::GetWindow(handle, GW_CHILD));
  }

  // Give Flutter, including plugins, an opportunity to handle window messages.
  if (flutter_controller_) {
    std::optional<LRESULT> result =
        flutter_controller_->HandleTopLevelWindowProc(hwnd, message, wparam,
                                                      lparam);
    if (result) {
      return *result;
    }
  }

  switch (message) {
    case WM_FONTCHANGE:
      flutter_controller_->engine()->ReloadSystemFonts();
      break;

    case WM_DROPFILES:
      HandleDroppedFiles(reinterpret_cast<HDROP>(wparam));
      return 0;

    case WM_CLOSE:
      // The quick panel has no title bar; Alt+F4 asks the shell to close it, so
      // treat it as "dismiss the HUD" rather than "hide the app".
      if (quick_mode_) {
        NotifyQuickDismissed();
        return 0;
      }
      // Legacy behaviour: the close button hides to the tray, it does not quit.
      if (!quitting_) {
        HideToTray();
        return 0;
      }
      break;

    case kTrayCallbackMessage:
      if (lparam == WM_LBUTTONUP || lparam == WM_LBUTTONDBLCLK) {
        ToggleVisibility();
        return 0;
      }
      if (lparam == WM_RBUTTONUP) {
        ShowTrayMenu();
        return 0;
      }
      break;

    case WM_COMMAND:
      switch (LOWORD(wparam)) {
        case kMenuToggle:
          ToggleVisibility();
          return 0;
        case kMenuExit:
          RequestQuit();
          return 0;
        default:
          break;
      }
      break;
  }

  return Win32Window::MessageHandler(hwnd, message, wparam, lparam);
}
