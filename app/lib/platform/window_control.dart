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
  static Future<void> exitQuickMode() => _invoke<void>('exitQuickMode');

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
