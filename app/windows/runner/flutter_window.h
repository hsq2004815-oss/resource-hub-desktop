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

  // Brings the window to the foreground even when the app does not own the
  // current foreground window (the global hotkey is handled by the Python
  // backend, so Windows' foreground lock would otherwise keep the panel behind
  // the previous app and the panel would never receive its dismissal/focus).
  void ForceForeground();

  // Phase 16: compact "quick panel" mode. The window keeps its Flutter engine but
  // temporarily drops its frame, becomes topmost and shrinks to the requested
  // logical size, so the same UI can render a Spotlight-style tree HUD. Restoring
  // puts the saved frame, rect and topmost state back.
  bool EnterQuickMode(int logical_width, int logical_height);

  // Leaves quick mode and restores the saved frame/rect. `visibility` picks what
  // happens to the window: 0 = return to the pre-quick state, 1 = always show,
  // 2 = always hide (the window is hidden before the geometry is restored so the
  // HUD-sized window never grows back on screen for a frame).
  void ExitQuickMode(int visibility = 0);

  // Tells Dart that the quick panel should close (focus was lost, tray click,
  // second instance, Alt+F4). Dart calls exitQuickMode() and restores its UI.
  void NotifyQuickDismissed();

  // While the HUD is up, watch the system foreground window. Some activation
  // hand-offs never deliver WM_ACTIVATE(WA_INACTIVE) to us (the panel was forced
  // to the foreground through AttachThreadInput), so a 100 ms timer is the
  // reliable "click-away" signal: once the panel had foreground, any other
  // process becoming foreground dismisses it (Phase 18.2).
  void StartQuickForegroundWatch();
  void StopQuickForegroundWatch();
  void CheckQuickForeground();

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

  // Quick-panel state (see EnterQuickMode).
  bool quick_mode_ = false;
  bool quick_was_visible_ = false;
  bool quick_dismiss_posted_ = false;
  // True from the start of EnterQuickMode until the activation hand-off has
  // settled: the spurious WM_ACTIVATE(WA_INACTIVE) produced while forcing the
  // foreground must not close the panel immediately.
  bool quick_activation_settling_ = false;
  // Set once the HUD itself has been the foreground window; only after that does
  // "another process owns the foreground" mean the user clicked away.
  bool quick_had_foreground_ = false;
  LONG_PTR quick_saved_style_ = 0;
  LONG_PTR quick_saved_ex_style_ = 0;
  RECT quick_saved_rect_ = {};
};

#endif  // RUNNER_FLUTTER_WINDOW_H_
