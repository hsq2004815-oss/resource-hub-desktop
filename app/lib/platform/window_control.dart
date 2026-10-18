/// Native window + tray control.
///
/// Implemented by `windows/runner/flutter_window.cpp` on the
/// `resource_hub/window` channel. Every call is a no-op when the platform
/// handler is absent (widget tests, non-Windows targets), so callers never need
/// to guard.
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
