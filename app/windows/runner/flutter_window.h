#ifndef RUNNER_FLUTTER_WINDOW_H_
#define RUNNER_FLUTTER_WINDOW_H_

#include <flutter/dart_project.h>
#include <flutter/encodable_value.h>
#include <flutter/flutter_view_controller.h>
#include <flutter/method_channel.h>

#include <memory>
#include <string>
#include <vector>

#include "win32_window.h"

// A window that hosts a Flutter view, plus the tray icon that keeps the app
// reachable while the window is hidden.
//
// Behaviour mirrors the legacy Tkinter app: closing the window hides it to the
// tray instead of quitting (`hide_to_tray`, resource_hub.pyw:1417), and the
// global hotkey toggles visibility.
class FlutterWindow : public Win32Window {
 public:
  // Creates a new FlutterWindow hosting a Flutter view running |project|.
  explicit FlutterWindow(const flutter::DartProject& project);
  virtual ~FlutterWindow();

 protected:
  // Win32Window:
  bool OnCreate() override;
  void OnDestroy() override;
  LRESULT MessageHandler(HWND window, UINT const message, WPARAM const wparam,
                         LPARAM const lparam) noexcept override;

 private:
  void RegisterChannels();
  void InstallTray();
  void RemoveTray();
  void ShowTrayMenu();
  void HideToTray();
  void ShowFromTray();
  void ToggleVisibility();
  void RequestQuit();
  bool IsWindowVisibleNow();

  // Hands shell paths (drag & drop) to the Dart side as UTF-8 strings.
  void PublishDroppedPaths(const std::vector<std::string>& paths);

  // Shared WM_DROPFILES handling for the top-level window and the Flutter view.
  void HandleDroppedFiles(HDROP drop);

  // The Flutter view covers the whole client area, so Explorer's drop lands on
  // it. The engine's WndProc does not handle WM_DROPFILES, so the view window is
  // subclassed to forward drops here (and re-attached if the engine recreates
  // the view window).
  void AttachDropTarget(HWND child);
  static LRESULT CALLBACK ChildWndProc(HWND window, UINT message,
                                       WPARAM wparam, LPARAM lparam) noexcept;

  // The project to run.
  flutter::DartProject project_;

  // The Flutter instance hosted by this window.
  std::unique_ptr<flutter::FlutterViewController> flutter_controller_;

  // `resource_hub/window` — window title, show/hide, tray labels and shell
  // dialogs (see ADR-002).
  std::unique_ptr<flutter::MethodChannel<flutter::EncodableValue>>
      window_channel_;

  bool tray_installed_ = false;
  bool quitting_ = false;

  // Flutter view window currently subclassed as a drop target.
  HWND child_window_ = nullptr;
  WNDPROC child_original_proc_ = nullptr;

  // Started by the Startup shortcut: stay hidden until the tray is clicked.
  bool startup_hidden_ = false;

  // Tray menu labels, pushed from Dart so they follow the UI language.
  std::wstring tray_toggle_label_ = L"Show / Hide";
  std::wstring tray_exit_label_ = L"Exit";
};

#endif  // RUNNER_FLUTTER_WINDOW_H_
