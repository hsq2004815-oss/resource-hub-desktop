/// Native window + tray control.
///
/// Implemented by `windows/runner/flutter_window.cpp` on the
/// `resource_hub/window` channel. Every call is a no-op when the platform
/// handler is absent (widget tests, non-Windows targets), so callers never need
/// to guard.
///
/// Incoming notifications (`quickDismissed`) are exposed by [NativeShell]: it is
/// the single owner of the channel's message handler, so two `setMethodCallHandler`
/// calls cannot overwrite each other.
library;

import 'package:flutter/services.dart';

/// What the runner should do with the main window after leaving quick mode.
enum QuickExitVisibility {
  /// Put the window back into the state it had before the panel opened.
  auto,

  /// Always show the restored full window (hotkey asks for the full app).
  show,

  /// Always hide it (the panel was opened over the tray).
  hide,
}

abstract final class WindowControl {
  static const MethodChannel _channel = MethodChannel('resource_hub/window');

  static Future<void> setTitle(String title) =>
      _invoke<void>('setTitle', title);

  /// Tray menu labels follow the UI language.
  static Future<void> setTrayLabels({
    required String toggle,
    required String exit,
  }) =>
      _invoke<void>('setTrayLabels', <String, String>{
        'toggle': toggle,
        'exit': exit,
      });

  /// Toggles visibility and returns whether the window is now visible.
  static Future<bool> toggle() async => await _invoke<bool>('toggle') ?? false;

  static Future<void> show() => _invoke<void>('show');

  static Future<void> hide() => _invoke<void>('hide');

  static Future<bool> isVisible() async =>
      await _invoke<bool>('isVisible') ?? false;

  /// Phase 16: shrinks the window into a frameless, topmost quick panel.
  ///
  /// [width] and [height] are logical pixels; the runner scales them to the
  /// monitor DPI and centres the panel on the monitor under the cursor.
  static Future<bool> enterQuickMode({
    required double width,
    required double height,
  }) async =>
      await _invoke<bool>('enterQuickMode', <String, double>{
        'width': width,
        'height': height,
      }) ??
      false;

  /// Restores the saved frame, size and visibility after [enterQuickMode].
  ///
  /// The runner hides the window before restoring the geometry when it is not
  /// going to stay visible, so the HUD-sized window never briefly grows back on
  /// screen with a stale frame.
  static Future<void> exitQuickMode({
    QuickExitVisibility visibility = QuickExitVisibility.auto,
  }) =>
      _invoke<void>('exitQuickMode', <String, String>{
        'visibility': visibility.name,
      });

  /// Destroys the window; the process exits and the backend sees stdin EOF.
  static Future<void> quit() => _invoke<void>('quit');

  static Future<T?> _invoke<T>(String method, [Object? arguments]) async {
    try {
      return await _channel.invokeMethod<T>(method, arguments);
    } on MissingPluginException {
      return null;
    } on PlatformException {
      // A cosmetic window operation must never break the UI.
      return null;
    }
  }
}
